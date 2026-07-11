"""
Single entry point for writing to PatientRecordAccessLog.

Keeping this in one place — instead of scattering `PatientRecordAccessLog.objects.create(...)`
calls across views — means the audit format can't drift, and it's easy to
verify every access path calls it (grep for `log_access`).
"""

from .models import PatientRecordAccessLog


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_access(*, patient, accessed_by, action, resource, request=None, reason=""):
    """
    patient: identity.patientAccount instance
    accessed_by: identity.Identity instance (request.user)
    action: one of PatientRecordAccessLog.ACTION_CHOICES
    resource: short string like f"ClinicalNote:{note.id}"
    """
    PatientRecordAccessLog.objects.create(
        patient=patient,
        accessed_by=accessed_by,
        action=action,
        resource=resource,
        reason=reason,
        ip_address=get_client_ip(request) if request else None,
    )
