"""
Run with:  python manage.py shell < smoke_test_hmis.py

Exercises the real hmis views/permissions/serializers end-to-end:
  create facility/provider/patient -> Encounter -> ClinicalNote -> sign it
  -> confirm editing a signed note is rejected -> confirm the access log
  picked up the activity.

Everything happens inside a transaction that is deliberately rolled back
at the end (via the RollbackTest exception), so nothing here touches
your real production data permanently. Safe to run directly against
the live Render shell.
"""
import jwt
from django.conf import settings
from django.db import transaction
from django.test import Client


class RollbackTest(Exception):
    pass


def make_token(identity):
    payload = {"user_id": str(identity.id)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def run():
    from identity.models import Identity, patientAccount, HealthcareProviderAccount, FacilityManagerAccount
    from facility.models import Facility
    from hmis.models import Encounter, ClinicalNote, PatientRecordAccessLog

    client = Client()

    owner_identity = Identity.objects.create(
        email="smoketest-owner@veridoctor.internal", first_name="Smoke", last_name="Owner", is_active=True
    )
    fm = FacilityManagerAccount.objects.create(identity=owner_identity)
    fac = Facility.objects.create(
        name="Smoke Test Facility", address="n/a", contact="n/a",
        type_of_facility="clinic", location="Nairobi", owner=fm,
    )

    prov_identity = Identity.objects.create(
        email="smoketest-prov@veridoctor.internal", first_name="Smoke", last_name="Provider", is_active=True
    )
    prov = HealthcareProviderAccount.objects.create(identity=prov_identity)

    pat_identity = Identity.objects.create(
        email="smoketest-pat@veridoctor.internal", first_name="Smoke", last_name="Patient", is_active=True
    )
    pat = patientAccount.objects.create(identity=pat_identity)

    prov_token = make_token(prov_identity)
    auth_header = {"HTTP_AUTHORIZATION": f"Bearer {prov_token}"}

    # 1. Create an encounter as the provider
    resp = client.post(
        "/api/hmis/encounters/",
        data={
            "patient": str(pat.id), "provider": str(prov.id), "facility": str(fac.id),
            "encounter_type": "OUTPATIENT", "status": "IN_PROGRESS",
        },
        content_type="application/json",
        **auth_header,
    )
    print("Create encounter:", resp.status_code, resp.content[:300])
    assert resp.status_code == 201, "Encounter creation failed"
    encounter_id = resp.json()["id"]

    # 2. Add a clinical note
    resp = client.post(
        "/api/hmis/clinical-notes/",
        data={"encounter": encounter_id, "content": "Smoke test note.", "note_type": "GENERAL"},
        content_type="application/json",
        **auth_header,
    )
    print("Create note:", resp.status_code, resp.content[:300])
    assert resp.status_code == 201, "Note creation failed"
    note_id = resp.json()["id"]

    # 3. Sign it directly at the model level (no dedicated endpoint yet)
    note = ClinicalNote.objects.get(id=note_id)
    note.sign()
    print("Note signed:", note.is_signed)

    # 4. Confirm editing a signed note is rejected by the API
    resp = client.patch(
        f"/api/hmis/clinical-notes/{note_id}/",
        data={"content": "tampered"},
        content_type="application/json",
        **auth_header,
    )
    print("Edit signed note (expect 400):", resp.status_code, resp.content[:300])
    assert resp.status_code == 400, "Signed note was editable — immutability broken!"

    # 5. Confirm access log picked up the activity
    log_count = PatientRecordAccessLog.objects.filter(patient=pat).count()
    print("Access log entries for this patient:", log_count)
    assert log_count > 0, "No access log entries were written"

    print("\nALL CHECKS PASSED")


try:
    with transaction.atomic():
        run()
        raise RollbackTest("rolling back smoke test data — this is expected, not an error")
except RollbackTest as e:
    print(f"\n(Rolled back cleanly: {e})")
