from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from rest_framework.permissions import BasePermission

UNLOCK_TOKEN_MAX_AGE = 15 * 60  # 15 minutes
_signer = TimestampSigner(salt="patient-records-unlock")


def generate_unlock_token(patient_identity_id):
    return _signer.sign(str(patient_identity_id))


def verify_unlock_token(token, patient_identity_id):
    if not token:
        return False
    try:
        value = _signer.unsign(token, max_age=UNLOCK_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return value == str(patient_identity_id)


class RecordsUnlockRequired(BasePermission):
    """
    Add to permission_classes on any view returning a patient's own
    health records (e.g. PatientTimelineView).
    Frontend sends header: X-Records-Unlock: <token>

    IMPORTANT: this only makes sense when request.user IS the patient
    whose records are being viewed — it checks the unlock token against
    request.user.id, not against any patient_identity_id in the URL. Do
    NOT put this on a view a provider can call about a different
    identity's records; request.user.id will be the provider's own id,
    which will never match a token signed for the patient, so it will
    unconditionally return False and return 403 to a caller who was
    never supposed to be PIN-gated in the first place (this is exactly
    what broke provider-side "Your records for this patient").
    """
    message = "Records PIN verification required or expired."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        token = request.headers.get("X-Records-Unlock")
        return verify_unlock_token(token, request.user.id)


class ProviderPatientRelationshipRequired(BasePermission):
    """
    Provider-side equivalent of RecordsUnlockRequired. A provider viewing
    records for a patient never has a PIN to unlock — instead, access is
    granted if the requesting provider has at least one non-cancelled
    ProviderAppointment with that patient (i.e. a genuine, pre-existing
    care relationship). This backs the "Your records for this patient —
    No consent needed" panel on the provider's appointment detail page,
    which is a fundamentally different access model from a patient
    viewing their own timeline and must not share RecordsUnlockRequired.

    Expects the view to have `patient_identity_id` in its URL kwargs.
    """
    message = "No existing care relationship found with this patient."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        patient_identity_id = view.kwargs.get("patient_identity_id")
        if not patient_identity_id:
            return False

        from provider.models import HealthcareProvider
        from appointments.models import ProviderAppointment

        try:
            provider = HealthcareProvider.objects.get(identity=request.user)
        except HealthcareProvider.DoesNotExist:
            return False

        return (
            ProviderAppointment.objects.filter(
                provider=provider,
                patient_identity__id=patient_identity_id,
            )
            .exclude(status="cancelled")
            .exists()
        )
