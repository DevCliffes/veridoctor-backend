"""
RBAC for HMIS resources, built entirely on relationships that already exist
in identity/facility — no separate "role" table to keep in sync.

Access is granted if the requesting Identity is:
  - the patient themself (via identity.patientAccount, read-only on their
    own encounters), or
  - a HealthcareProviderAccount attached to the encounter, or
  - assigned staff on a Workstation belonging to the encounter's facility
    (facility.Workstation.assigned_staff), or
  - a FacilityManagerAccount/BranchManagerAccount for that facility.

Every check here is a *necessary* gate, not a sufficient one — callers must
still invoke hmis.audit.log_access on every read/write that touches a
patient record.
"""

from rest_framework.permissions import BasePermission


def _is_facility_staff(user, facility):
    if facility.owner.identity_id == user.id:
        return True
    if facility.managers.filter(identity=user).exists():
        return True
    return facility.workstations.filter(assigned_staff=user).exists()


class CanAccessEncounter(BasePermission):
    """Object-level permission for Encounter and everything hanging off it."""

    def has_object_permission(self, request, view, obj):
        encounter = getattr(obj, "encounter", obj)
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if getattr(encounter.patient, "identity_id", None) == user.id:
            return request.method in ("GET", "HEAD", "OPTIONS")

        if encounter.provider and encounter.provider.identity_id == user.id:
            return True

        return _is_facility_staff(user, encounter.facility)


class CanAccessPatientRecord(BasePermission):
    """Object-level permission for anything scoped directly by patient (Invoice, ConsentRecord, ...)."""

    def has_object_permission(self, request, view, obj):
        patient = getattr(obj, "patient", obj)
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if patient.identity_id == user.id:
            return request.method in ("GET", "HEAD", "OPTIONS")

        facility = getattr(obj, "facility", None)
        if facility is not None and _is_facility_staff(user, facility):
            return True

        return patient.encounters.filter(
            provider__identity=user
        ).exists() or patient.encounters.filter(
            facility__workstations__assigned_staff=user
        ).exists()
