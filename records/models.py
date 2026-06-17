from django.db import models
from identity.models import Identity
from provider.models import HealthcareProvider
from shared.models import BaseModel


class PatientProviderRecordSummary(BaseModel):
    """
    Lightweight, non-clinical index of what records a patient has with a
    given provider. Lets other providers see 'this patient has N records
    here, last updated on X' without exposing any clinical content —
    actual access to that content requires a separate consent grant
    (built in the next batch).
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
