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
    """
    message = "Records PIN verification required or expired."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        token = request.headers.get("X-Records-Unlock")
        return verify_unlock_token(token, request.user.id)
