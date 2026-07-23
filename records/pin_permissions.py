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
    THEIR OWN records -- it never compared that identity against the
    patient_identity_id in the URL. That meant any authenticated patient
    who unlocked their own PIN once could reuse that same valid token to
    view ANY other patient's timeline just by changing the URL's
    patient_identity_id. Now we require request.user to actually BE the
    patient_identity_id being requested, in addition to holding a valid
    unlock token for themselves.

    Still only makes sense on views identifying the patient via a
    `patient_identity_id` URL kwarg. Do NOT put this on a provider-facing
    view -- see ProviderPatientRelationshipRequired instead.
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

    FIX: previously did not check request.user at all -- it only verified
    that the provider_id/patient_identity_id pair in the URL had a real,
    non-cancelled appointment between them, regardless of who the caller
    actually was. That meant anyone who could guess or enumerate a valid
    (provider_id, patient_identity_id) pair -- authenticated or not --
    could pass this check without being that provider. This was written
    that way because, at the time, apps/provider did not attach an
    Authorization header, so requiring request.user would have rejected
    every legitimate request. apps/provider (served from
    provider.veridoctor.com) now attaches a Bearer token via
    maybeAuthoriseProvider() in axios-client.ts on every non-public
    request, so request.user is reliably populated and can be checked.

    Access is granted only if:
      1. The caller is authenticated, AND
      2. The caller IS the provider identified by the `provider_id` URL
         kwarg, AND
      3. That provider has at least one non-cancelled ProviderAppointment
         with the patient identified by `patient_identity_id`.
    """
    message = "No existing care relationship found with this patient."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        provider_identity_id = view.kwargs.get("provider_id")
        patient_identity_id = view.kwargs.get("patient_identity_id")
        if not provider_identity_id or not patient_identity_id:
            return False

        # The caller must actually BE the provider named in the URL.
        if str(request.user.id) != str(provider_identity_id):
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
