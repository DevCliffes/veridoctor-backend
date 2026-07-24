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
        ("completed", "Completed"),
        ("rescheduled", "Rescheduled"),
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
        max_length=20, choices=STATUS_CHOICES, default="confirmed"
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
    service = models.ForeignKey(
        "provider.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    patient_identity = models.ForeignKey(
        "identity.Identity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_appointments",
        help_text="Linked automatically by matching patient_email to an "
                   "Identity at booking time. May be null for older "
                   "records until the backfill command links them.",
    )
    # Which of the provider's facilities this appointment is/was at.
    # Null for virtual appointments (location-less by design, same rule
    # as ProviderSchedule) and for physical appointments booked before
    # this field existed, until backfilled. SET_NULL rather than CASCADE
    # for the same reason as ProviderSchedule.location: deleting a
    # facility shouldn't delete appointment history tied to it -- the
    # appointment just loses its location reference.
    location = models.ForeignKey(
        "provider.ProviderLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
    )
    appointment_type = models.CharField(
        max_length=20, choices=APPOINTMENT_TYPE_CHOICES, default="virtual"
    )
    message = models.TextField(blank=True)
    meet_id = models.CharField(max_length=32, unique=True, blank=True)
    # Real-world timestamps captured when status actually transitions to
    # in-progress / completed — distinct from start_time/end_time, which
    # are just the scheduled slot and never move once booked (aside from
    # reschedules). "Avg. Duration" on the dashboard is computed from
    # these, so it reflects how long consultations actually took rather
    # than how long the slot was booked for.
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)

    # Snapshot of the service's price/currency at the moment this
    # appointment was created — deliberately NOT a live reference to
    # Service.price. Revenue reporting (ProviderDashboardStatsView) must
    # reflect what was actually charged at booking time, not whatever the
    # provider's price list says today. Without this, editing a service's
    # price retroactively changes past months' reported revenue, and
    # deleting a service (service is SET_NULL) makes past revenue vanish
    # entirely. Null on historical rows created before this field existed
    # until backfilled.
    price_at_booking = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    currency_at_booking = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        ordering = ["start_time"]

    def save(self, *args, **kwargs):
        if not self.meet_id:
            self.meet_id = get_random_string(16)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient_first_name} {self.patient_last_name} - {self.start_time}"


class AppointmentCapture(BaseModel):
    """Patient data captured during a consultation using a provider form."""
    appointment = models.ForeignKey(
        ProviderAppointment,
        on_delete=models.CASCADE,
        related_name="captures",
    )
    form_id = models.CharField(max_length=255)
    form_name = models.CharField(max_length=255, blank=True)
    form_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="Snapshot of the form sections at the time of capture, "
                  "so data remains readable even if the form is later edited or deleted."
    )
    values = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Capture for {self.appointment} — {self.form_name}"
