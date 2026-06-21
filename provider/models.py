from django.db import models
import uuid
from identity.models import Identity


class HealthcareProvider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identity = models.OneToOneField(Identity, on_delete=models.CASCADE, related_name="provider_profile")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    licence_number = models.CharField(max_length=100, blank=True, null=True)
    licence_type = models.CharField(max_length=100, blank=True, null=True)
    speciality = models.CharField(max_length=100, blank=True, null=True)
    title = models.CharField(max_length=20, blank=True, null=True, default="Dr.")
    clinic_name = models.CharField(max_length=200, blank=True, null=True)
    address = models.CharField(max_length=300, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True, default="Kenya")
    bio = models.TextField(blank=True, null=True)
    insurances_accepted = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    profile_picture_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.identity} — {self.speciality or 'Provider'}"


class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(HealthcareProvider, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=200)
    estimated_duration = models.IntegerField(help_text="Duration in minutes")
    # null=True, blank=True — price is optional. Providers can leave it blank
    # to indicate the price is negotiable and agreed between provider and patient.
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default="KES")
    description = models.TextField(blank=True, null=True)
    price_visible = models.BooleanField(
        default=True,
        help_text="Whether the price is shown publicly to patients when booking"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Form(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(HealthcareProvider, on_delete=models.CASCADE, related_name="forms")
    name = models.CharField(max_length=200)
    sections = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Prescription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(HealthcareProvider, on_delete=models.CASCADE, related_name="prescriptions")
    patient_id = models.CharField(max_length=255, blank=True)
    patient_name = models.CharField(max_length=255, blank=True, null=True)
    patient_email = models.EmailField(blank=True, null=True, db_index=True)
    patient_identity = models.ForeignKey(
        Identity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions_received",
        help_text="Linked automatically by matching patient_email to an "
                   "Identity at creation time. May be null for older "
                   "records until the backfill command links them.",
    )
    diagnosis = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Prescription for {self.patient_name} by {self.provider}"


class PrescriptionDrug(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="drugs")
    drug_name = models.CharField(max_length=255)
    dosage = models.CharField(max_length=100, blank=True, null=True)
    frequency = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    instructions = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.drug_name


class ProviderSchedule(models.Model):
    LOCATION_CHOICES = [
        ("virtual", "virtual"),
        ("physical", "physical"),
        ("both", "both"),
    ]
    RECURRENCE_CHOICES = [
        ("none", "none"),
        ("daily", "daily"),
        ("weekdays", "weekdays"),
        ("weekly", "weekly"),
        ("custom", "custom"),
    ]
    END_TYPE_CHOICES = [
        ("never", "never"),
        ("on_date", "on_date"),
        ("after", "after"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        HealthcareProvider, on_delete=models.CASCADE, related_name="schedules"
    )
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True, related_name="schedules"
    )
    location_type = models.CharField(max_length=10, choices=LOCATION_CHOICES, default="virtual")

    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    recurrence = models.CharField(max_length=10, choices=RECURRENCE_CHOICES, default="none")
    recurrence_interval = models.PositiveIntegerField(default=1)
    recurrence_days = models.JSONField(default=list, blank=True)
    recurrence_end_type = models.CharField(
        max_length=10, choices=END_TYPE_CHOICES, null=True, blank=True
    )
    recurrence_end_date = models.DateField(null=True, blank=True)
    recurrence_count = models.PositiveIntegerField(null=True, blank=True)
    excluded_dates = models.JSONField(
        default=list,
        blank=True,
        help_text="ISO date strings (YYYY-MM-DD) to skip for recurring schedules — "
                   "used when deleting/editing a single occurrence instead of the whole series."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        title = self.service.name if self.service else "Schedule"
        return f"{title} ({self.start_date})"
