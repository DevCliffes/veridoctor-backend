from django.db import models
from identity.models import Identity
from provider.models import HealthcareProvider
from shared.models import BaseModel
from .pin_models import PatientRecordsPin  # noqa


class PatientProviderRecordSummary(BaseModel):
    """
    Lightweight, non-clinical index of what records a patient has with a
    given provider.
    """
    SENSITIVITY_CHOICES = [
        ("always_visible", "Always visible to other providers"),
        ("ask_first", "Ask patient before requesting"),
        ("never", "Never visible to other providers"),
    ]
    patient_identity = models.ForeignKey(
        Identity, on_delete=models.CASCADE, related_name="record_summaries"
    )
    provider = models.ForeignKey(
        HealthcareProvider, on_delete=models.CASCADE, related_name="patient_summaries"
    )
    record_count = models.PositiveIntegerField(default=0)
    last_record_at = models.DateTimeField(null=True, blank=True)
    sensitivity = models.CharField(
        max_length=20, choices=SENSITIVITY_CHOICES, default="ask_first"
    )

    class Meta:
        unique_together = ("patient_identity", "provider")
        ordering = ["-last_record_at"]

    def __str__(self):
        return f"{self.patient_identity} @ {self.provider} ({self.record_count} records)"


class RecordAccessGrant(BaseModel):
    """
    Tracks a provider's request to access a patient's records from another
    provider/facility. Patient approves or denies via the health portal.
    Scoped to a specific consultation — intent is that access expires when
    that appointment ends (enforced at the API layer, not DB level, so
    historical grants remain auditable).

    GDPR Art. 9: explicit consent for special-category health data.
    UHR: audit trail of who accessed what and when.
    """
    STATUS_CHOICES = [
        ("pending", "Pending — awaiting patient response"),
        ("approved", "Approved by patient"),
        ("denied", "Denied by patient"),
    ]

    patient_identity = models.ForeignKey(
        Identity,
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    requesting_provider = models.ForeignKey(
        HealthcareProvider,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    appointment = models.ForeignKey(
        "appointments.ProviderAppointment",
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    requested_category = models.CharField(
        max_length=255,
        help_text="Speciality/category of records requested e.g. 'Cardiology'",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (
            "patient_identity",
            "requesting_provider",
            "appointment",
            "requested_category",
        )
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.requesting_provider} → {self.patient_identity} "
            f"[{self.requested_category}] ({self.status})"
        )
