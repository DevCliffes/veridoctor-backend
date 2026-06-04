from django.db import models
from shared.models import BaseModel
from django.core.exceptions import ValidationError


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


# class ProviderAppointment(BaseAppointment):
#     """Purpose: Clinical consultations with a specific doctor"""

#     provider = models.ForeignKey("provider.Provider", on_delete=models.CASCADE)
#     reason_for_visit = models.TextField()
#     clinical_notes = models.TextField(blank=True)


# class FacilityAppointment(BaseAppointment):
#     """Purpose: Equipment/Room bookings (MRI, Lab, Surgery Suite)"""

#     facility = models.ForeignKey("facility.Facility", on_delete=models.CASCADE)
#     equipment_required = models.CharField(max_length=100, blank=True)
#     prep_instructions = models.TextField(help_text="e.g., Fast for 12 hours")

