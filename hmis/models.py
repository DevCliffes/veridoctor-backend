"""
HMIS core: encounters, clinical documentation, orders, billing, consent,
and access audit trail.

Design principles this module follows:
  - No duplicate concepts. Patient/Provider/Facility are the existing
    identity.patientAccount, identity.HealthcareProviderAccount, and
    facility.Facility records — HMIS only adds clinical/billing data
    that hangs off of them.
  - Clinical records are append-only where compliance demands it.
    Signed clinical notes are never edited in place (see ClinicalNote.sign
    and ClinicalNoteAddendum); PatientRecordAccessLog rows are never
    deleted or updated by application code.
  - PROTECT (not CASCADE) is used on FKs where deleting the parent would
    silently destroy a legally/medically significant record (encounters,
    invoices, diagnoses tied to a provider, etc). Soft-delete the parent
    via BaseModel's own mechanism instead of hard-deleting it.
"""

from django.db import models
from shared.models import BaseModel


# ---------------------------------------------------------------------------
# Encounters
# ---------------------------------------------------------------------------

class Encounter(BaseModel):
    """A single clinical visit/interaction — the spine everything else hangs off."""

    ENCOUNTER_TYPE_CHOICES = [
        ("OUTPATIENT", "Outpatient"),
        ("INPATIENT", "Inpatient"),
        ("EMERGENCY", "Emergency"),
        ("TELEHEALTH", "Telehealth"),
        ("FOLLOWUP", "Follow-up"),
    ]
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("CHECKED_IN", "Checked In"),
        ("IN_PROGRESS", "In Progress"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
        ("NO_SHOW", "No Show"),
    ]

    patient = models.ForeignKey(
        "identity.patientAccount", on_delete=models.PROTECT, related_name="encounters"
    )
    provider = models.ForeignKey(
        "identity.HealthcareProviderAccount", on_delete=models.PROTECT,
        related_name="encounters", null=True, blank=True,
    )
    facility = models.ForeignKey(
        "facility.Facility", on_delete=models.PROTECT, related_name="encounters"
    )
    workstation = models.ForeignKey(
        "facility.Workstation", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="encounters",
    )
    encounter_type = models.CharField(max_length=20, choices=ENCOUNTER_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="SCHEDULED")
    reason_for_visit = models.TextField(blank=True, default="")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        "identity.Identity", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="closed_encounters",
        help_text="Provider/staff who formally closed out the encounter",
    )

    class Meta:
        indexes = [
            models.Index(fields=["patient", "-scheduled_at"]),
            models.Index(fields=["facility", "status"]),
        ]

    def __str__(self):
        return f"Encounter({self.patient.patient_uid}, {self.encounter_type}, {self.status})"


class VitalSigns(BaseModel):
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="vitals")
    recorded_by = models.ForeignKey(
        "identity.Identity", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    temperature_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    blood_pressure_systolic = models.IntegerField(null=True, blank=True)
    blood_pressure_diastolic = models.IntegerField(null=True, blank=True)
    pulse_bpm = models.IntegerField(null=True, blank=True)
    respiratory_rate = models.IntegerField(null=True, blank=True)
    spo2_percent = models.IntegerField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------------
# Clinical documentation
# ---------------------------------------------------------------------------

class ClinicalNote(BaseModel):
    """
    SOAP-style clinical note. Immutable once signed: compliant clinical
    records are never rewritten after the fact. Corrections happen via
    ClinicalNoteAddendum, which preserves the original alongside the fix.
    """

    NOTE_TYPE_CHOICES = [
        ("SUBJECTIVE", "Subjective"),
        ("OBJECTIVE", "Objective"),
        ("ASSESSMENT", "Assessment"),
        ("PLAN", "Plan"),
        ("GENERAL", "General"),
    ]

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        "identity.HealthcareProviderAccount", on_delete=models.PROTECT, related_name="clinical_notes"
    )
    note_type = models.CharField(max_length=20, choices=NOTE_TYPE_CHOICES, default="GENERAL")
    content = models.TextField()
    is_signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)

    def sign(self):
        from django.utils import timezone
        if self.is_signed:
            raise ValueError("Note is already signed; corrections must go through an addendum.")
        self.is_signed = True
        self.signed_at = timezone.now()
        self.save(update_fields=["is_signed", "signed_at"])

    def save(self, *args, **kwargs):
        if self.pk:
            original = ClinicalNote.objects.filter(pk=self.pk).only("is_signed").first()
            if original and original.is_signed:
                raise ValueError(
                    "Signed clinical notes are immutable. Add a ClinicalNoteAddendum instead."
                )
        super().save(*args, **kwargs)


class ClinicalNoteAddendum(BaseModel):
    """Append-only correction/addition to a signed note."""

    note = models.ForeignKey(ClinicalNote, on_delete=models.CASCADE, related_name="addenda")
    author = models.ForeignKey("identity.HealthcareProviderAccount", on_delete=models.PROTECT)
    content = models.TextField()


class Diagnosis(BaseModel):
    DIAGNOSIS_TYPE_CHOICES = [
        ("PRIMARY", "Primary"),
        ("SECONDARY", "Secondary"),
        ("DIFFERENTIAL", "Differential"),
        ("RULED_OUT", "Ruled Out"),
    ]

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="diagnoses")
    icd10_code = models.CharField(max_length=10)
    description = models.CharField(max_length=500)
    diagnosis_type = models.CharField(max_length=20, choices=DIAGNOSIS_TYPE_CHOICES, default="PRIMARY")
    diagnosed_by = models.ForeignKey("identity.HealthcareProviderAccount", on_delete=models.PROTECT)
    diagnosed_at = models.DateTimeField(auto_now_add=True)


class MedicationOrder(BaseModel):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("ACTIVE", "Active"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="medication_orders")
    medication_name = models.CharField(max_length=255)
    dosage = models.CharField(max_length=100)
    route = models.CharField(max_length=50, blank=True, default="")
    frequency = models.CharField(max_length=100)
    duration = models.CharField(max_length=100, blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    prescribed_by = models.ForeignKey("identity.HealthcareProviderAccount", on_delete=models.PROTECT)
    prescribed_at = models.DateTimeField(auto_now_add=True)


class LabOrder(BaseModel):
    STATUS_CHOICES = [
        ("ORDERED", "Ordered"),
        ("SPECIMEN_COLLECTED", "Specimen Collected"),
        ("IN_PROGRESS", "In Progress"),
        ("RESULTED", "Resulted"),
        ("CANCELLED", "Cancelled"),
    ]

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="lab_orders")
    test_name = models.CharField(max_length=255)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="ORDERED")
    ordered_by = models.ForeignKey(
        "identity.HealthcareProviderAccount", on_delete=models.PROTECT, related_name="lab_orders_placed"
    )
    ordered_at = models.DateTimeField(auto_now_add=True)


class LabResult(BaseModel):
    lab_order = models.OneToOneField(LabOrder, on_delete=models.CASCADE, related_name="result")
    result_value = models.TextField(blank=True, default="")
    result_file = models.FileField(upload_to="lab_results/%Y/%m/", null=True, blank=True)
    reference_range = models.CharField(max_length=255, blank=True, default="")
    is_abnormal = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        "identity.HealthcareProviderAccount", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lab_results_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resulted_at = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

class Invoice(BaseModel):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("ISSUED", "Issued"),
        ("PARTIALLY_PAID", "Partially Paid"),
        ("PAID", "Paid"),
        ("VOID", "Void"),
    ]

    encounter = models.ForeignKey(Encounter, on_delete=models.PROTECT, related_name="invoices")
    patient = models.ForeignKey("identity.patientAccount", on_delete=models.PROTECT, related_name="invoices")
    facility = models.ForeignKey("facility.Facility", on_delete=models.PROTECT, related_name="invoices")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    currency = models.CharField(max_length=3, default="KES")
    issued_at = models.DateTimeField(null=True, blank=True)

    @property
    def total_amount(self):
        return sum((item.line_total for item in self.line_items.all()), 0)

    @property
    def amount_paid(self):
        return sum((p.amount for p in self.payments.all()), 0)

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid


class InvoiceLineItem(BaseModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items")
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class Payment(BaseModel):
    METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("MPESA", "M-Pesa"),
        ("CARD", "Card"),
        ("INSURANCE", "Insurance"),
        ("BANK_TRANSFER", "Bank Transfer"),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=255, blank=True, default="")
    received_by = models.ForeignKey("identity.Identity", on_delete=models.SET_NULL, null=True, related_name="+")
    paid_at = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------------
# Consent & audit — the compliance backbone
# ---------------------------------------------------------------------------

class ConsentRecord(BaseModel):
    """
    Patient consent for treatment / data sharing / research. Required under
    Kenya's Data Protection Act 2019 for handling special-category (health)
    personal data, and standard practice for any HMIS regardless of
    jurisdiction. Consent is revoked, never deleted.
    """

    CONSENT_TYPE_CHOICES = [
        ("TREATMENT", "Treatment"),
        ("DATA_SHARING", "Data Sharing"),
        ("RESEARCH", "Research"),
    ]

    patient = models.ForeignKey("identity.patientAccount", on_delete=models.CASCADE, related_name="consents")
    consent_type = models.CharField(max_length=20, choices=CONSENT_TYPE_CHOICES)
    is_granted = models.BooleanField(default=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    witnessed_by = models.ForeignKey(
        "identity.Identity", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def revoke(self):
        from django.utils import timezone
        self.is_granted = False
        self.revoked_at = timezone.now()
        self.save(update_fields=["is_granted", "revoked_at"])


class PatientRecordAccessLog(BaseModel):
    """
    Append-only audit trail of who touched a patient's record, when, how,
    and why. This is the single most important compliance model in the
    app — write to it from every view/serializer that reads or writes
    clinical data (see hmis.audit.log_access). It must never expose an
    update or delete path anywhere in the codebase, including admin.
    """

    ACTION_CHOICES = [
        ("VIEW", "View"),
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("EXPORT", "Export"),
    ]

    patient = models.ForeignKey("identity.patientAccount", on_delete=models.CASCADE, related_name="access_logs")
    accessed_by = models.ForeignKey("identity.Identity", on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    resource = models.CharField(max_length=100, help_text="e.g. 'ClinicalNote:<uuid>'")
    reason = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["patient", "-accessed_at"]),
        ]
