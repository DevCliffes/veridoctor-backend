from django.db import models
import uuid
from django.conf import settings
from identity.models import Identity
from django.db import models
from django.core.exceptions import ValidationError


# ── Shared review status / rejection-category choices ──────────────────────
# Used by both ProviderDocumentReview (personal docs) and
# ProviderLocationDocumentReview (per-location facility docs) so the two
# review queues behave identically from an admin's point of view.
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_CHOICES = [
    (REVIEW_STATUS_PENDING, "Pending review"),
    (REVIEW_STATUS_APPROVED, "Approved"),
    (REVIEW_STATUS_REJECTED, "Rejected"),
]

REJECTION_INCORRECT = "incorrect"
REJECTION_UNCLEAR = "unclear"
REJECTION_INCOMPLETE = "incomplete"
REJECTION_OTHER = "other"
REJECTION_CATEGORY_CHOICES = [
    (REJECTION_INCORRECT, "Incorrect document (wrong type / doesn't match provider)"),
    (REJECTION_UNCLEAR, "Unclear (blurry, cropped, low resolution, glare)"),
    (REJECTION_INCOMPLETE, "Incomplete (missing pages, expired, partial info)"),
    (REJECTION_OTHER, "Other"),
]


class HealthcareProvider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identity = models.OneToOneField(Identity, on_delete=models.CASCADE, related_name="provider_profile")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    licence_number = models.CharField(max_length=100, blank=True, null=True)
    licence_type = models.CharField(max_length=100, blank=True, null=True)
    speciality = models.CharField(max_length=100, blank=True, null=True)
    subspecialties = models.JSONField(default=list, blank=True)
    title = models.CharField(max_length=20, blank=True, null=True, default="Dr.")
    bio = models.TextField(blank=True, null=True)
    insurances_accepted = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    profile_picture_url = models.URLField(blank=True, null=True)

    # ── Personal identification ───────────────────────────────────────────────
    national_id_number = models.CharField(max_length=50, blank=True, default="")
    national_id_image = models.CharField(max_length=500, blank=True, default="")

    # ── Professional credentials ───────────────────────────────────────────────
    valid_licence_number = models.CharField(max_length=100, blank=True, default="")
    valid_licence_image = models.CharField(max_length=500, blank=True, default="")
    extra_credentials = models.JSONField(
        default=list,
        blank=True,
        help_text="List of additional credentials e.g. [{'id': '...', 'name': 'KMPDB', 'number': '...', 'image_url': '...'}]",
    )

    # NOTE: clinic_name, address, county, country, clinic_logo_url,
    # business_reg_number/image, operating_licence(_image), kra_pin(_image),
    # and cr12_image used to live here. They have moved to ProviderLocation
    # below, since a provider can now have more than one practice location.
    # See the data migration for how existing rows are backfilled into each
    # provider's first (is_primary=True) ProviderLocation.

    # ── Profile completeness tracking ───────────────────────────────────────────
    # Kept as a real DB column (instead of a computed property only) so it can be
    # filtered/counted efficiently in the admin and on the dashboard.
    # Excludes: subspecialties, languages, insurances_accepted, extra_credentials
    # (all optional/enrichment fields, not required for booking).
    # NOTE: profile_complete now means "personal fields complete AND at least
    # one ProviderLocation is itself data-complete" -- it does NOT mean the
    # provider is approved/bookable. See is_bookable for that.
    profile_complete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    REQUIRED_TEXT_FIELDS = [
        "phone_number",
        "licence_number",
        "licence_type",
        "speciality",
        "bio",
        "national_id_number",
        "valid_licence_number",
    ]
    REQUIRED_IMAGE_FIELDS = [
        "profile_picture_url",
        "national_id_image",
        "valid_licence_image",
    ]

    def missing_fields(self):
        """Return a list of required field names that are blank/missing.
        Personal/professional fields only -- facility completeness is
        tracked separately per ProviderLocation."""
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
        """Recalculate and return whether the profile is complete, without saving.
        True once personal fields are filled in AND at least one
        ProviderLocation has all of its own required fields filled in.
        This is purely about data entry -- it says nothing about admin
        approval status (see is_bookable for that)."""
        if len(self.missing_fields()) != 0:
            return False
        return self.locations.filter(data_complete=True).exists()

    @property
    def credentials_approved(self):
        """True once both personal documents (national ID, valid licence)
        have been reviewed and approved."""
        required = {"national_id_image", "valid_licence_image"}
        reviews = {
            r.field_name: r.status
            for r in self.document_reviews.filter(field_name__in=required)
        }
        return all(reviews.get(f) == REVIEW_STATUS_APPROVED for f in required)

    @property
    def is_bookable(self):
        """True once personal credentials are approved AND at least one
        location is fully approved. This -- not profile_complete -- is
        what should gate patient-facing visibility/search."""
        return self.credentials_approved and self.locations.filter(
            is_fully_approved_cache=True
        ).exists()

    def save(self, *args, **kwargs):
        self.profile_complete = self.recompute_profile_complete()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.identity} — {self.speciality or 'Provider'}"


class ProviderLocation(models.Model):
    """
    A single practice location for a provider (a clinic, hospital branch,
    or other physical address they see patients at). A provider who works
    across multiple facilities has one row per facility.

    This is intentionally separate from facility.Facility, which models
    an institutional facility account (owned by a FacilityManagerAccount,
    with its own managers/workstations/branches) -- a different domain
    entirely from a provider self-reporting their own practice address.

    Editing ANY tracked field (text or document) resets every document
    review on this location back to pending -- an approved location that
    changes its address, county, name, or re-uploads a document is no
    longer bookable until an admin reviews and approves it again. This
    mirrors the existing per-document reset behaviour in
    ProviderDocumentReview, just scoped to the whole location rather than
    a single field.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(
        HealthcareProvider, on_delete=models.CASCADE, related_name="locations"
    )

    name = models.CharField(max_length=200, blank=True, default="")
    address = models.CharField(max_length=300, blank=True, default="")
    county = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="Kenya")

    clinic_logo_url = models.CharField(max_length=500, blank=True, default="")
    business_reg_number = models.CharField(max_length=100, blank=True, default="")
    business_reg_image = models.CharField(max_length=500, blank=True, default="")
    operating_licence = models.CharField(max_length=100, blank=True, default="")
    operating_licence_image = models.CharField(max_length=500, blank=True, default="")
    kra_pin = models.CharField(max_length=50, blank=True, default="")
    kra_pin_image = models.CharField(max_length=500, blank=True, default="")
    cr12_image = models.CharField(max_length=500, blank=True, default="")

    is_primary = models.BooleanField(
        default=False,
        help_text="The location backfilled from this provider's original single-facility "
                   "data, or otherwise designated as their main/default location.",
    )

    # Stored (not computed-only) for the same reason profile_complete is
    # stored on HealthcareProvider: cheap filtering/counting in the admin
    # and in recompute_profile_complete()/is_bookable above.
    data_complete = models.BooleanField(default=False)
    is_fully_approved_cache = models.BooleanField(
        default=False,
        help_text="Denormalized copy of is_fully_approved, kept in sync on save() "
                   "and whenever a ProviderLocationDocumentReview changes, so "
                   "HealthcareProvider.is_bookable can filter on it directly "
                   "instead of evaluating a Python property per row.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_TEXT_FIELDS = [
        "name",
        "address",
        "county",
        "business_reg_number",
        "operating_licence",
        "kra_pin",
    ]
    REQUIRED_IMAGE_FIELDS = [
        "clinic_logo_url",
        "business_reg_image",
        "operating_licence_image",
        "kra_pin_image",
        "cr12_image",
    ]

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def missing_fields(self):
        missing = []
        for field in self.REQUIRED_TEXT_FIELDS + self.REQUIRED_IMAGE_FIELDS:
            value = getattr(self, field, None)
            if value is None or str(value).strip() == "":
                missing.append(field)
        return missing

    def recompute_is_fully_approved(self):
        """True only once every required document field has an approved
        ProviderLocationDocumentReview row. A location with a pending or
        rejected document -- or one that hasn't been reviewed at all
        yet -- is not bookable."""
        approved_fields = set(
            self.document_reviews.filter(status=REVIEW_STATUS_APPROVED).values_list(
                "field_name", flat=True
            )
        )
        return set(self.REQUIRED_IMAGE_FIELDS).issubset(approved_fields)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        reset_reviews = False

        if not is_new:
            try:
                original = ProviderLocation.objects.get(pk=self.pk)
                tracked_fields = self.REQUIRED_TEXT_FIELDS + self.REQUIRED_IMAGE_FIELDS
                reset_reviews = any(
                    getattr(original, f) != getattr(self, f) for f in tracked_fields
                )
            except ProviderLocation.DoesNotExist:
                reset_reviews = False

        self.data_complete = len(self.missing_fields()) == 0

        if reset_reviews:
            # Any tracked field changed on an existing location -- every
            # document on it needs re-review, so it drops out of
            # is_bookable until an admin approves it again.
            self.is_fully_approved_cache = False
        elif not is_new:
            self.is_fully_approved_cache = self.recompute_is_fully_approved()

        super().save(*args, **kwargs)

        if reset_reviews:
            self.document_reviews.update(
                status=REVIEW_STATUS_PENDING,
                rejection_category="",
                rejection_reason="",
                reviewed_at=None,
                reviewed_by=None,
            )

    def __str__(self):
        return f"{self.name or 'Location'} — {self.provider}"


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

    # A schedule block is only tied to a specific ProviderLocation when it
    # can involve seeing patients in person -- i.e. location_type is
    # "physical" or "both". A purely "virtual" block has no facility
    # attached (null), since the whole point of virtual care is that it
    # isn't tied to a place. Enforced in the view layer (see
    # ProviderScheduleView.post / ProviderScheduleDetailView.patch), not
    # at the DB level, since the requirement depends on location_type,
    # which a plain FK constraint can't express.
    #
    # on_delete=SET_NULL rather than CASCADE: if a location is deleted,
    # existing schedule blocks that referenced it shouldn't vanish --
    # they fall back to unscoped (null), same as a virtual block, rather
    # than silently deleting a provider's whole recurring availability
    # because they removed one facility.
    location = models.ForeignKey(
        ProviderLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules",
    )

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


# Personal/professional documents only. Facility documents now live on
# ProviderLocationDocumentReview below, keyed by location instead of
# provider, since a provider can have more than one facility.
DOCUMENT_FIELD_CHOICES = [
    ("national_id_image", "National ID"),
    ("valid_licence_image", "Valid Licence"),
]


class ProviderDocumentReview(models.Model):
    """
    Tracks approval status per individual personal/professional document
    field on a provider (National ID, valid operating licence), rather
    than one status for the whole profile. Each row corresponds to one
    document field for one provider.

    Whenever a provider re-uploads a document (see
    ProviderDocumentUploadView.post / _reset_document_review), the
    matching row here is reset to "pending" regardless of its previous
    state — so an admin's earlier approval never silently carries over
    to a new file. Approved documents stay approved only until the
    provider uploads a replacement.
    """

    STATUS_PENDING = REVIEW_STATUS_PENDING
    STATUS_APPROVED = REVIEW_STATUS_APPROVED
    STATUS_REJECTED = REVIEW_STATUS_REJECTED
    STATUS_CHOICES = REVIEW_STATUS_CHOICES

    REJECTION_INCORRECT = REJECTION_INCORRECT
    REJECTION_UNCLEAR = REJECTION_UNCLEAR
    REJECTION_INCOMPLETE = REJECTION_INCOMPLETE
    REJECTION_OTHER = REJECTION_OTHER
    REJECTION_CATEGORY_CHOICES = REJECTION_CATEGORY_CHOICES

    provider = models.ForeignKey(
        HealthcareProvider,
        on_delete=models.CASCADE,
        related_name="document_reviews",
    )
    field_name = models.CharField(max_length=64, choices=DOCUMENT_FIELD_CHOICES)
    document_url = models.URLField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    rejection_category = models.CharField(
        max_length=16, choices=REJECTION_CATEGORY_CHOICES, blank=True, default=""
    )
    rejection_reason = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("provider", "field_name")
        ordering = ["provider", "field_name"]

    def __str__(self):
        return f"{self.provider} — {self.get_field_name_display()} ({self.status})"


# Facility documents, scoped to a single ProviderLocation.
LOCATION_DOCUMENT_FIELD_CHOICES = [
    ("clinic_logo_url", "Clinic Logo"),
    ("business_reg_image", "Business Registration"),
    ("operating_licence_image", "Operating Licence"),
    ("kra_pin_image", "KRA PIN"),
    ("cr12_image", "CR12"),
]


class ProviderLocationDocumentReview(models.Model):
    """
    The per-location counterpart to ProviderDocumentReview. Tracks
    approval status per document field on a single ProviderLocation, so
    a provider with several facilities has each one reviewed
    independently -- one location can be fully approved and bookable
    while another sits pending.

    `unique_together` is keyed on (location, field_name) rather than
    including provider at all, since location already implies provider.
    Unlike ProviderDocumentReview, location is never null, so this
    constraint is always enforced at the database level (a nullable FK
    in the constraint would let Postgres silently allow duplicate NULLs).

    Rows here are bulk-reset to pending by ProviderLocation.save()
    whenever any tracked field on the location changes -- not just when
    a specific document is replaced. See ProviderLocation's docstring.
    """

    STATUS_PENDING = REVIEW_STATUS_PENDING
    STATUS_APPROVED = REVIEW_STATUS_APPROVED
    STATUS_REJECTED = REVIEW_STATUS_REJECTED
    STATUS_CHOICES = REVIEW_STATUS_CHOICES

    REJECTION_INCORRECT = REJECTION_INCORRECT
    REJECTION_UNCLEAR = REJECTION_UNCLEAR
    REJECTION_INCOMPLETE = REJECTION_INCOMPLETE
    REJECTION_OTHER = REJECTION_OTHER
    REJECTION_CATEGORY_CHOICES = REJECTION_CATEGORY_CHOICES

    location = models.ForeignKey(
        ProviderLocation,
        on_delete=models.CASCADE,
        related_name="document_reviews",
    )
    field_name = models.CharField(max_length=64, choices=LOCATION_DOCUMENT_FIELD_CHOICES)
    document_url = models.URLField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    rejection_category = models.CharField(
        max_length=16, choices=REJECTION_CATEGORY_CHOICES, blank=True, default=""
    )
    rejection_reason = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("location", "field_name")
        ordering = ["location", "field_name"]

    def __str__(self):
        return f"{self.location} — {self.get_field_name_display()} ({self.status})"
