from django.db import models
from shared.models import BaseModel
from django.core.exceptions import ValidationError
from django.utils.crypto import get_random_string


class BaseAppointment(models.Model):
    """Common fields for any type of appointment"""

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("confirmed", "Confirmed"),
        ("in-progress", "In-progress"),
        ("cancelled", "Cancelled"),
        ("no-show", "No-show"),
    ]

    patient_first_name = models.CharField(max_length=255)
    patient_last_name = models.CharField(max_length=255)
    patient_email = models.EmailField(blank=True)
    patient_phone_number = models.CharField(max_length=255, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="scheduled"
    )

    class Meta:
        abstract = True

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time.")


class ProviderAppointment(BaseAppointment, BaseModel):
    """Clinical consultations with a specific provider."""

    APPOINTMENT_TYPE_CHOICES = [
        ("virtual", "Virtual"),
        ("physical", "Physical"),
    ]

    provider = models.ForeignKey(
        "provider.HealthcareProvider",
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    appointment_type = models.CharField(
        max_length=20, choices=APPOINTMENT_TYPE_CHOICES, default="virtual"
    )
    message = models.TextField(blank=True)
    meet_id = models.CharField(max_length=32, unique=True, blank=True)

    class Meta:
        ordering = ["start_time"]

    def save(self, *args, **kwargs):
        if not self.meet_id:
            self.meet_id = get_random_string(16)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient_first_name} {self.patient_last_name} - {self.start_time}"


# class FacilityAppointment(BaseAppointment):
#     """Purpose: Equipment/Room bookings (MRI, Lab, Surgery Suite)"""

#     facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE)
#     equipment_required = models.CharField(max_length=100, blank=True)
#     prep_instructions = models.TextField(help_text="e.g., Fast for 12 hours")
