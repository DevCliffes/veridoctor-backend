from django.db import models
from shared.models import BaseModel


class Facility(BaseModel):
    """
    A healthcare facility
    """

    class Meta:
        verbose_name = "Facility"
        verbose_name_plural = "Facilities"

    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    contact = models.CharField(max_length=50)
    type_of_facility = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    owner = models.ForeignKey(
        "identity.FacilityManagerAccount",
        on_delete=models.CASCADE,
        related_name="facilities_owned",
    )

    # branch facilities
    parent_facility = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="branches"
    )

    managers = models.ManyToManyField(
        "identity.BranchManagerAccount", blank=True, related_name="facilities_managed"
    )

    def __str__(self):
        return f"{self.name}"


class Workstation(BaseModel):
    """
    A workstation in a healthcare facility
    """

    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    facility = models.ForeignKey(
        "Facility", on_delete=models.CASCADE, related_name="workstations"
    )

    assigned_staff = models.ManyToManyField(
        "identity.Identity", blank=True, related_name="assigned_staff"
    )
