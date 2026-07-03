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
    Provider-side equivalent of RecordsUnlockRequired.

    NOTE: unlike RecordsUnlockRequired, this does NOT rely on
    request.user — the provider frontend does not currently attach a
    Bearer token to its requests (no provider endpoint in this codebase
    enforces IsAuthenticated; every one of them trusts an identity_id
    passed explicitly in the URL instead). Using request.user here would
    mean this permission fails unconditionally for every real provider
    request, which is exactly what caused the 401 -> redirect-to-login
    loop when this was first written against IsAuthenticated.

    Access is granted if the provider identified by the `provider_id`
    URL kwarg has at least one non-cancelled ProviderAppointment with the
    patient identified by `patient_identity_id`.
    """
    message = "No existing care relationship found with this patient."

    def has_permission(self, request, view):
        provider_identity_id = view.kwargs.get("provider_id")
        patient_identity_id = view.kwargs.get("patient_identity_id")
        if not provider_identity_id or not patient_identity_id:
            return False

        from provider.models import HealthcareProvider
        from appointments.models import ProviderAppointment

        try:
            provider = HealthcareProvider.objects.get(identity__id=provider_identity_id)
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
