from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from identity.models import Identity
from provider.models import HealthcareProvider
from .models import PatientProviderRecordSummary, RecordAccessGrant
from .serializers import PatientProviderRecordSummarySerializer
from .pin_permissions import RecordsUnlockRequired, ProviderPatientRelationshipRequired


class PatientRecordSummaryView(APIView):
    def get(self, request, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        exclude_provider_identity_id = request.query_params.get("exclude_provider")
        summaries = PatientProviderRecordSummary.objects.filter(
            patient_identity=patient_identity
        ).select_related("provider", "provider__identity")

        if exclude_provider_identity_id:
            try:
                exclude_provider = HealthcareProvider.objects.get(
                    identity__id=exclude_provider_identity_id
                )
                summaries = summaries.exclude(provider=exclude_provider)
            except HealthcareProvider.DoesNotExist:
                pass

        serializer = PatientProviderRecordSummarySerializer(summaries, many=True)
        return Response(serializer.data)


class PatientTimelineView(APIView):
    """
    Patient-facing clinical timeline across AppointmentCapture,
    Prescription, and ProviderAppointment.

    Gated by RecordsUnlockRequired — this is only for a patient viewing
    their OWN records. Providers must use ProviderPatientTimelineView
    below instead, which is gated by an actual care relationship rather
    than a PIN.

    Query params:
      type     — filter by record type: "consultation" or "prescription"
      provider — filter consultations to a specific provider (identity_id).
    """
    permission_classes = [IsAuthenticated, RecordsUnlockRequired]

    def get(self, request, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        record_type = request.query_params.get("type")
        provider_identity_id = request.query_params.get("provider")

        from appointments.models import ProviderAppointment, AppointmentCapture
        from provider.models import Prescription

        records = []

        if not record_type or record_type == "consultation":
            appointments = ProviderAppointment.objects.filter(
                patient_identity=patient_identity,
            ).exclude(status="cancelled").select_related(
                "provider", "provider__identity", "service"
            ).prefetch_related("captures").order_by("-start_time")

            if provider_identity_id:
                try:
                    provider = HealthcareProvider.objects.get(
                        identity__id=provider_identity_id
                    )
                    appointments = appointments.filter(provider=provider)
                except HealthcareProvider.DoesNotExist:
                    appointments = appointments.none()

            sensitivity_map = {}
            summaries = PatientProviderRecordSummary.objects.filter(
                patient_identity=patient_identity
            ).values("provider_id", "sensitivity", "id")
            for s in summaries:
                sensitivity_map[s["provider_id"]] = {
                    "sensitivity": s["sensitivity"],
                    "summary_id": str(s["id"]),
                }

            for appt in appointments:
                captures = []
                for cap in appt.captures.all():
                    captures.append({
                        "form_name": cap.form_name,
                        "form_snapshot": cap.form_snapshot,
                        "values": cap.values,
                        "captured_at": cap.created_at.isoformat(),
                    })
                provider_info = sensitivity_map.get(appt.provider_id, {})
                records.append({
                    "id": str(appt.id),
                    "fhir_resource_type": "Encounter",
                    "record_type": "consultation",
                    "date": appt.start_time.isoformat(),
                    "provider_name": f"Dr. {appt.provider.identity.first_name} {appt.provider.identity.last_name}",
                    "speciality": appt.provider.speciality or "",
                    "facility_name": appt.provider.clinic_name or "",
                    "county": appt.provider.county or "",
                    "appointment_type": appt.appointment_type,
                    "status": appt.status,
                    "service_name": appt.service.name if appt.service else None,
                    "captures": captures,
                    "has_clinical_notes": len(captures) > 0,
                    "sensitivity": provider_info.get("sensitivity", "ask_first"),
                    "summary_id": provider_info.get("summary_id"),
                })

        if not record_type or record_type == "prescription":
            prescriptions = Prescription.objects.filter(
                patient_identity=patient_identity,
            ).select_related(
                "provider", "provider__identity"
            ).prefetch_related("drugs").order_by("-created_at")

            for rx in prescriptions:
                drugs = []
                for drug in rx.drugs.all():
                    drugs.append({
                        "drug_name": drug.drug_name,
                        "dosage": drug.dosage,
                        "frequency": drug.frequency,
                        "duration": drug.duration,
                        "instructions": drug.instructions,
                    })
                records.append({
                    "id": str(rx.id),
                    "fhir_resource_type": "MedicationRequest",
                    "record_type": "prescription",
                    "date": rx.created_at.isoformat(),
                    "provider_name": f"Dr. {rx.provider.identity.first_name} {rx.provider.identity.last_name}",
                    "speciality": rx.provider.speciality or "",
                    "facility_name": rx.provider.clinic_name or "",
                    "county": rx.provider.county or "",
                    "diagnosis": rx.diagnosis,
                    "notes": rx.notes,
                    "drugs": drugs,
                    "sensitivity": None,
                    "summary_id": None,
                })

        records.sort(key=lambda r: r["date"], reverse=True)

        return Response({
            "patient_id": str(patient_identity.id),
            "total": len(records),
            "records": records,
        })


class ProviderPatientTimelineView(APIView):
    """
    Provider-facing view of records THIS SPECIFIC PROVIDER created for a
    patient — backs "Your records for this patient" in the provider's
    AppointmentDetailPage, which explicitly requires no patient consent.

    Gated by ProviderPatientRelationshipRequired (imported from
    pin_permissions above), which checks an existing appointment
    relationship using provider_id/patient_identity_id taken directly
    from the URL — matching how every other provider view in this
    codebase identifies the requester, since the provider frontend does
    not attach an Authorization header and IsAuthenticated would
    therefore reject every legitimate request.
    """
    permission_classes = [ProviderPatientRelationshipRequired]

    def get(self, request, provider_id, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            provider = HealthcareProvider.objects.get(identity__id=provider_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        record_type = request.query_params.get("type")

        from appointments.models import ProviderAppointment
        from provider.models import Prescription

        records = []

        if not record_type or record_type == "consultation":
            appointments = ProviderAppointment.objects.filter(
                patient_identity=patient_identity,
                provider=provider,
            ).exclude(status="cancelled").select_related(
                "provider", "provider__identity", "service"
            ).prefetch_related("captures").order_by("-start_time")

            for appt in appointments:
                captures = []
                for cap in appt.captures.all():
                    captures.append({
                        "form_name": cap.form_name,
                        "form_snapshot": cap.form_snapshot,
                        "values": cap.values,
                        "captured_at": cap.created_at.isoformat(),
                    })
                records.append({
                    "id": str(appt.id),
                    "fhir_resource_type": "Encounter",
                    "record_type": "consultation",
                    "date": appt.start_time.isoformat(),
                    "provider_name": f"Dr. {appt.provider.identity.first_name} {appt.provider.identity.last_name}",
                    "speciality": appt.provider.speciality or "",
                    "facility_name": appt.provider.clinic_name or "",
                    "county": appt.provider.county or "",
                    "appointment_type": appt.appointment_type,
                    "status": appt.status,
                    "service_name": appt.service.name if appt.service else None,
                    "captures": captures,
                    "has_clinical_notes": len(captures) > 0,
                })

        if not record_type or record_type == "prescription":
            prescriptions = Prescription.objects.filter(
                patient_identity=patient_identity,
                provider=provider,
            ).select_related(
                "provider", "provider__identity"
            ).prefetch_related("drugs").order_by("-created_at")

            for rx in prescriptions:
                drugs = []
                for drug in rx.drugs.all():
                    drugs.append({
                        "drug_name": drug.drug_name,
                        "dosage": drug.dosage,
                        "frequency": drug.frequency,
                        "duration": drug.duration,
                        "instructions": drug.instructions,
                    })
                records.append({
                    "id": str(rx.id),
                    "fhir_resource_type": "MedicationRequest",
                    "record_type": "prescription",
                    "date": rx.created_at.isoformat(),
                    "provider_name": f"Dr. {rx.provider.identity.first_name} {rx.provider.identity.last_name}",
                    "speciality": rx.provider.speciality or "",
                    "facility_name": rx.provider.clinic_name or "",
                    "county": rx.provider.county or "",
                    "diagnosis": rx.diagnosis,
                    "notes": rx.notes,
                    "drugs": drugs,
                })

        records.sort(key=lambda r: r["date"], reverse=True)

        return Response({
            "patient_id": str(patient_identity.id),
            "total": len(records),
            "records": records,
        })


class ProviderPatientSummaryView(APIView):
    def get(self, request, appointment_id):
        from appointments.models import ProviderAppointment
        from provider.models import Prescription

        try:
            appointment = ProviderAppointment.objects.select_related(
                "patient_identity", "provider", "provider__identity"
            ).get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        patient_identity = appointment.patient_identity
        if not patient_identity:
            return Response(
                {"error": "No patient identity linked to this appointment"},
                status=status.HTTP_404_NOT_FOUND,
            )

        requesting_provider = appointment.provider

        try:
            from identity.models import patientAccount
            patient_acct = patientAccount.objects.get(identity=patient_identity)
            patient_uid = patient_acct.patient_uid
            date_of_birth = (
                patient_acct.date_of_birth.isoformat()
                if patient_acct.date_of_birth
                else None
            )
            blood_type = patient_acct.blood_type
            allergies = patient_acct.allergies or []
            insurances = patient_acct.insurances or []
        except Exception:
            patient_uid = None
            date_of_birth = None
            blood_type = None
            allergies = []
            insurances = []

        summaries = PatientProviderRecordSummary.objects.filter(
            patient_identity=patient_identity
        ).select_related("provider", "provider__identity")

        total_records = sum(s.record_count for s in summaries)
        last_dates = [s.last_record_at for s in summaries if s.last_record_at]
        most_recent = max(last_dates).isoformat() if last_dates else None
        prior_facilities = summaries.count()

        active_meds = Prescription.objects.filter(
            patient_identity=patient_identity
        ).count()

        other_summaries = summaries.exclude(provider=requesting_provider)

        grants = RecordAccessGrant.objects.filter(
            appointment=appointment,
            patient_identity=patient_identity,
        )
        grants_by_category = {g.requested_category: g for g in grants}

        record_categories = []
        for s in other_summaries:
            category_key = s.provider.speciality or s.provider.clinic_name or "General"
            grant = grants_by_category.get(category_key)
            record_categories.append({
                "speciality": s.provider.speciality or "General Practice",
                "facility_name": s.provider.clinic_name or "",
                "record_count": s.record_count,
                "last_record_at": s.last_record_at.isoformat() if s.last_record_at else None,
                "sensitivity": s.sensitivity,
                "access_status": grant.status if grant else None,
                "grant_id": str(grant.id) if grant else None,
            })

        approved_grants = [
            {
                "id": str(g.id),
                "requested_category": g.requested_category,
                "status": g.status,
                "responded_at": g.responded_at.isoformat() if g.responded_at else None,
            }
            for g in grants
            if g.status == "approved"
        ]

        return Response({
            "patient": {
                "uid": patient_uid,
                "identity_id": str(patient_identity.id),
                "first_name": patient_identity.first_name,
                "last_name": patient_identity.last_name,
                "gender": patient_identity.gender or "UNKNOWN",
                "date_of_birth": date_of_birth,
                "blood_type": blood_type,
            },
            "consultation_active": appointment.status in ["confirmed", "in-progress"],
            "stats": {
                "total_records": total_records,
                "most_recent": most_recent,
                "active_medications": active_meds,
                "prior_facilities": prior_facilities,
            },
            "always_visible": {
                "allergies": allergies,
                "active_medications_count": active_meds,
                "insurances": insurances,
            },
            "record_categories": record_categories,
            "access_granted": approved_grants,
        })


class RecordAccessRequestView(APIView):
    def post(self, request):
        from appointments.models import ProviderAppointment

        appointment_id = request.data.get("appointment_id")
        requested_category = request.data.get("requested_category")
        provider_identity_id = request.data.get("provider_identity_id")

        if not all([appointment_id, requested_category, provider_identity_id]):
            return Response(
                {"error": "appointment_id, requested_category, and provider_identity_id are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            appointment = ProviderAppointment.objects.get(id=appointment_id)
            provider = HealthcareProvider.objects.get(identity__id=provider_identity_id)
        except (ProviderAppointment.DoesNotExist, HealthcareProvider.DoesNotExist):
            return Response({"error": "Appointment or provider not found"}, status=status.HTTP_404_NOT_FOUND)

        patient_identity = appointment.patient_identity
        if not patient_identity:
            return Response(
                {"error": "No patient identity linked to this appointment"},
                status=status.HTTP_404_NOT_FOUND,
            )

        grant, created = RecordAccessGrant.objects.get_or_create(
            patient_identity=patient_identity,
            requesting_provider=provider,
            appointment=appointment,
            requested_category=requested_category,
            defaults={"status": "pending"},
        )

        if not created and grant.status == "denied":
            grant.status = "pending"
            grant.responded_at = None
            grant.save(update_fields=["status", "responded_at", "updated_at"])

        return Response(
            {
                "id": str(grant.id),
                "requested_category": grant.requested_category,
                "status": grant.status,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PatientAccessRequestsView(APIView):
    def get(self, request, patient_identity_id):
        try:
            patient_identity = Identity.objects.get(id=patient_identity_id)
        except Identity.DoesNotExist:
            return Response({"error": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

        grants = RecordAccessGrant.objects.filter(
            patient_identity=patient_identity,
        ).select_related(
            "requesting_provider",
            "requesting_provider__identity",
            "appointment",
        ).order_by("-created_at")

        data = [
            {
                "id": str(g.id),
                "requested_category": g.requested_category,
                "status": g.status,
                "provider_name": (
                    f"Dr. {g.requesting_provider.identity.first_name} "
                    f"{g.requesting_provider.identity.last_name}"
                ),
                "provider_speciality": g.requesting_provider.speciality or "",
                "facility_name": g.requesting_provider.clinic_name or "",
                "appointment_date": g.appointment.start_time.isoformat(),
                "created_at": g.created_at.isoformat(),
                "responded_at": g.responded_at.isoformat() if g.responded_at else None,
            }
            for g in grants
        ]

        return Response(data)


class RecordAccessGrantDetailView(APIView):
    """
    Patient approves or denies an access request.
    PATCH /records/access-grants/<grant_id>
    """
    def patch(self, request, grant_id):
        new_status = request.data.get("status")
        if new_status not in ("approved", "denied"):
            return Response(
                {"error": "status must be 'approved' or 'denied'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            grant = RecordAccessGrant.objects.get(id=grant_id)
        except RecordAccessGrant.DoesNotExist:
            return Response({"error": "Grant not found"}, status=status.HTTP_404_NOT_FOUND)

        grant.status = new_status
        grant.responded_at = timezone.now()
        grant.save(update_fields=["status", "responded_at", "updated_at"])

        return Response({
            "id": str(grant.id),
            "status": grant.status,
            "responded_at": grant.responded_at.isoformat(),
        })


class PatientSensitivityView(APIView):
    """
    Patient updates the sensitivity setting for records from a specific
    provider relationship (PatientProviderRecordSummary).

    PATCH /records/sensitivity/<summary_id>
    Body: { "sensitivity": "always_visible" | "ask_first" | "never" }
    """
    def patch(self, request, summary_id):
        VALID = {"always_visible", "ask_first", "never"}
        new_sensitivity = request.data.get("sensitivity")

        if new_sensitivity not in VALID:
            return Response(
                {"error": f"sensitivity must be one of: {', '.join(VALID)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            summary = PatientProviderRecordSummary.objects.get(id=summary_id)
        except PatientProviderRecordSummary.DoesNotExist:
            return Response({"error": "Record summary not found"}, status=status.HTTP_404_NOT_FOUND)

        summary.sensitivity = new_sensitivity
        summary.save(update_fields=["sensitivity", "updated_at"])

        return Response({
            "id": str(summary.id),
            "sensitivity": summary.sensitivity,
        })

class ProviderGrantedRecordsView(APIView):
    """
    Lets a requesting provider view the ACTUAL record contents for a
    patient category they've been granted access to via RecordAccessGrant.

    This is the missing piece: ProviderPatientSummaryView only ever
    returns grant metadata (status/count), and ProviderPatientTimelineView
    only returns records THIS provider created. Neither can show another
    provider's records even after the patient approves — this view closes
    that gap.

    GET /records/provider/<provider_id>/appointment/<appointment_id>/granted-records/<category>

    Gated by ProviderPatientRelationshipRequired (same permission class
    used by ProviderPatientTimelineView) — confirms provider_id has a real
    appointment relationship with the patient linked to appointment_id.
    On top of that, this view additionally requires a matching APPROVED
    RecordAccessGrant for this exact appointment + provider + category,
    since the relationship check alone isn't consent to view a DIFFERENT
    provider's records.
    """
    permission_classes = [ProviderPatientRelationshipRequired]

    def get(self, request, provider_id, appointment_id, category):
        from appointments.models import ProviderAppointment
        from provider.models import Prescription

        try:
            appointment = ProviderAppointment.objects.select_related(
                "patient_identity", "provider"
            ).get(id=appointment_id)
        except ProviderAppointment.DoesNotExist:
            return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

        patient_identity = appointment.patient_identity
        if not patient_identity:
            return Response(
                {"error": "No patient identity linked to this appointment"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            requesting_provider = HealthcareProvider.objects.get(identity__id=provider_id)
        except HealthcareProvider.DoesNotExist:
            return Response({"error": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)

        # The relationship permission class confirms provider_id has SOME
        # appointment with this patient — it does not confirm this is the
        # SAME appointment/consultation the grant was scoped to. Enforce
        # that explicitly here.
        if appointment.provider_id != requesting_provider.id:
            return Response(
                {"error": "This provider is not the requester on this appointment"},
                status=status.HTTP_403_FORBIDDEN,
            )

        grant = RecordAccessGrant.objects.filter(
            appointment=appointment,
            patient_identity=patient_identity,
            requesting_provider=requesting_provider,
            requested_category=category,
            status="approved",
        ).first()

        if not grant:
            return Response(
                {"error": "No approved access grant for this category on this appointment"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Access is scoped to the consultation it was granted for — the
        # RecordAccessGrant model's own docstring says this is enforced
        # at the API layer, but no existing view actually did it. Same
        # 30-minute grace window already used elsewhere in this codebase
        # (CALL_WINDOW_MS on the frontend, POLL_TOLERANCE for reminders)
        # so a provider isn't cut off mid-review right as the appointment
        # ends, but access doesn't stay open indefinitely either.
        from datetime import timedelta
        GRACE_PERIOD = timedelta(minutes=30)
        if timezone.now() > appointment.end_time + GRACE_PERIOD:
            return Response(
                {"error": "Access to this consultation's granted records has expired"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Resolve which OTHER providers fall under this category label —
        # categories are grouped by speciality/clinic_name string in
        # ProviderPatientSummaryView, so mirror that exact logic here to
        # stay consistent with what the patient was shown before approving.
        other_summaries = PatientProviderRecordSummary.objects.filter(
            patient_identity=patient_identity,
        ).exclude(provider=requesting_provider).select_related("provider", "provider__identity")

        matching_provider_ids = [
            s.provider_id for s in other_summaries
            if (s.provider.speciality or s.provider.clinic_name or "General Practice") == category
        ]

        if not matching_provider_ids:
            return Response({"category": category, "total": 0, "records": []})

        records = []

        appointments = ProviderAppointment.objects.filter(
            patient_identity=patient_identity,
            provider_id__in=matching_provider_ids,
        ).exclude(status="cancelled").select_related(
            "provider", "provider__identity", "service"
        ).prefetch_related("captures").order_by("-start_time")

        for appt in appointments:
            captures = []
            for cap in appt.captures.all():
                captures.append({
                    "form_name": cap.form_name,
                    "form_snapshot": cap.form_snapshot,
                    "values": cap.values,
                    "captured_at": cap.created_at.isoformat(),
                })
            records.append({
                "id": str(appt.id),
                "record_type": "consultation",
                "date": appt.start_time.isoformat(),
                "provider_name": f"Dr. {appt.provider.identity.first_name} {appt.provider.identity.last_name}",
                "speciality": appt.provider.speciality or "",
                "facility_name": appt.provider.clinic_name or "",
                "appointment_type": appt.appointment_type,
                "status": appt.status,
                "service_name": appt.service.name if appt.service else None,
                "captures": captures,
                "has_clinical_notes": len(captures) > 0,
            })

        prescriptions = Prescription.objects.filter(
            patient_identity=patient_identity,
            provider_id__in=matching_provider_ids,
        ).select_related("provider", "provider__identity").prefetch_related("drugs").order_by("-created_at")

        for rx in prescriptions:
            drugs = []
            for drug in rx.drugs.all():
                drugs.append({
                    "drug_name": drug.drug_name,
                    "dosage": drug.dosage,
                    "frequency": drug.frequency,
                    "duration": drug.duration,
                    "instructions": drug.instructions,
                })
            records.append({
                "id": str(rx.id),
                "record_type": "prescription",
                "date": rx.created_at.isoformat(),
                "provider_name": f"Dr. {rx.provider.identity.first_name} {rx.provider.identity.last_name}",
                "speciality": rx.provider.speciality or "",
                "facility_name": rx.provider.clinic_name or "",
                "diagnosis": rx.diagnosis,
                "notes": rx.notes,
                "drugs": drugs,
            })

        records.sort(key=lambda r: r["date"], reverse=True)

        return Response({
            "category": category,
            "total": len(records),
            "records": records,
        })
