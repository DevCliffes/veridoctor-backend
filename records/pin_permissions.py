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

    FIX: this previously only checked that request.user had unlocked
    THEIR OWN records — it never compared that identity against the
    patient_identity_id in the URL. That meant any authenticated patient
    who unlocked their own PIN once could reuse that same valid token to
    view ANY other patient's timeline just by changing the URL's
    patient_identity_id. Now we require request.user to actually BE the
    patient_identity_id being requested, in addition to holding a valid
    unlock token for themselves.

    Still only makes sense on views identifying the patient via a
    `patient_identity_id` URL kwarg. Do NOT put this on a provider-facing
    view — see ProviderPatientRelationshipRequired instead.
    """
    message = "Records PIN verification required or expired."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        patient_identity_id = view.kwargs.get("patient_identity_id")
        if not patient_identity_id or str(request.user.id) != str(patient_identity_id):
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

    TODO (security): this is a known gap, tracked separately — it grants
    access based on URL-supplied IDs having a real relationship, not on
    verifying the caller's identity. Needs provider frontend to attach
    auth tokens before this can check request.user like its patient-side
    counterpart does. See conversation/ticket on provider auth rollout.

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
