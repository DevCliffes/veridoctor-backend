from django.db import models
import uuid
from identity.models import Identity
from django.db import models
from django.core.exceptions import ValidationError


class HealthcareProvider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identity = models.OneToOneField(Identity, on_delete=models.CASCADE, related_name="provider_profile")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    licence_number = models.CharField(max_length=100, blank=True, null=True)
    licence_type = models.CharField(max_length=100, blank=True, null=True)
    speciality = models.CharField(max_length=100, blank=True, null=True)
    subspecialties = models.JSONField(default=list, blank=True)
    title = models.CharField(max_length=20, blank=True, null=True, default="Dr.")
    clinic_name = models.CharField(max_length=200, blank=True, null=True)
    address = models.CharField(max_length=300, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True, default="Kenya")
    bio = models.TextField(blank=True, null=True)
    insurances_accepted = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    profile_picture_url = models.URLField(blank=True, null=True)

    # ── Personal identification ───────────────────────────────────────────────
    national_id_number = models.CharField(max_length=50, blank=True, default="")
    national_id_image = models.CharField(max_length=500, blank=True, default="")

    # ── Practice & location documents ─────────────────────────────────────────
    clinic_logo_url = models.CharField(max_length=500, blank=True, default="")
    business_reg_number = models.CharField(max_length=100, blank=True, default="")
    business_reg_image = models.CharField(max_length=500, blank=True, default="")
    operating_licence = models.CharField(max_length=100, blank=True, default="")
    operating_licence_image = models.CharField(max_length=500, blank=True, default="")
    kra_pin = models.CharField(max_length=50, blank=True, default="")
    kra_pin_image = models.CharField(max_length=500, blank=True, default="")
    cr12_image = models.CharField(max_length=500, blank=True, default="")

    # ── Professional credentials ───────────────────────────────────────────────
    valid_licence_number = models.CharField(max_length=100, blank=True, default="")
    valid_licence_image = models.CharField(max_length=500, blank=True, default="")
    extra_credentials = models.JSONField(
        default=list,
        blank=True,
        help_text="List of additional credentials e.g. [{'id': '...', 'name': 'KMPDB', 'number': '...', 'image_url': '...'}]",
    )

    # ── Profile completeness tracking ───────────────────────────────────────────
    # Kept as a real DB column (instead of a computed property only) so it can be
    # filtered/counted efficiently in the admin and on the dashboard.
    # Excludes: subspecialties, languages, insurances_accepted, extra_credentials
    # (all optional/enrichment fields, not required for booking).
    profile_complete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    REQUIRED_TEXT_FIELDS = [
        "phone_number",
        "licence_number",
        "licence_type",
        "speciality",
        "clinic_name",
        "address",
        "county",
        "country",
        "bio",
        "national_id_number",
        "business_reg_number",
        "operating_licence",
        "kra_pin",
        "valid_licence_number",
    ]
    REQUIRED_IMAGE_FIELDS = [
        "profile_picture_url",
        "national_id_image",
        "clinic_logo_url",
        "business_reg_image",
        "operating_licence_image",
        "kra_pin_image",
        "cr12_image",
        "valid_licence_image",
    ]

    def missing_fields(self):
        """Return a list of required field names that are blank/missing."""
        missing = []
        for field in self.REQUIRED_TEXT_FIELDS + self.REQUIRED_IMAGE_FIELDS:
            value = getattr(self, field, None)
            if value is None or str(value).strip() == "":
                missing.append(field)
        if not (self.identity.first_name and self.identity.first_name.strip()):
            missing.append("first_name")
        if not (self.identity.last_name and self.identity.last_name.strip()):
            missing.append("last_name")
        return missing

    def recompute_profile_complete(self):
        """Recalculate and return whether the profile is complete, without saving."""
        return len(self.missing_fields()) == 0

    def save(self, *args, **kwargs):
        self.profile_complete = self.recompute_profile_complete()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.identity} — {self.speciality or 'Provider'}"


class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(HealthcareProvider, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=200)
    estimated_duration = models.IntegerField(help_text="Duration in minutes")
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


class ProviderReview(models.Model):
    """A patient's star rating and comment for a provider. Tied to the
    appointment that earned the right to review, so only patients who
    actually had a completed consultation can leave one. Public-facing
    display should only ever show patient_first_name — never
    patient_last_name, patient_email, or patient_identity — to keep the
    reviewer semi-anonymous while still attributable."""

    provider = models.ForeignKey(
        "provider.HealthcareProvider",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    appointment = models.OneToOneField(
        "appointments.ProviderAppointment",
        on_delete=models.CASCADE,
        related_name="review",
        help_text="The completed appointment this review is attached to. "
                   "One review per appointment, which naturally limits a "
                   "patient to one review per provider per visit.",
    )
    patient_identity = models.ForeignKey(
        "identity.Identity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_reviews",
    )
    patient_first_name = models.CharField(
        max_length=255,
        help_text="Denormalized at creation time — this is the only "
                   "patient-identifying field ever exposed publicly.",
    )
    patient_last_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Stored for moderation/support purposes only. Never "
                   "serialize this field in any public-facing response.",
    )
    rating = models.PositiveSmallIntegerField(
        help_text="1 to 5 stars."
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if not (1 <= self.rating <= 5):
            raise ValidationError("Rating must be between 1 and 5.")

    def __str__(self):
        return f"{self.patient_first_name} → {self.provider} ({self.rating}★)"
