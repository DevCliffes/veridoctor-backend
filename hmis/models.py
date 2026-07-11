"""
HMIS Core Models — Phase 1: Patient Registration, EMR, Billing

Design principle: internal storage stays simple and Django-idiomatic, but
wherever a field maps to a coded clinical concept (diagnosis, allergy,
vital sign type), it is stored in a FHIR `Coding`-shaped structure:
{system, code, display}. This costs nothing extra to build now, and lets
us generate valid FHIR JSON later via a thin export layer (Phase 5) without
redesigning the data model or migrating existing records.

Multi-tenancy: every clinical/billing record is scoped by `facility`
(ForeignKey), enforced at the application/query layer. This is the single
most important architectural decision in this file — do not remove
facility scoping from any model below when extending this app.
"""

import uuid
from django.conf import settings
from django.db import models


class Facility(models.Model):
    """A hospital/clinic using the HMIS."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    kmpdc_facility_code = models.CharField(max_length=50, blank=True, null=True)
    sha_facility_code = models.CharField(max_length=50, blank=True, null=True)
    county = models.CharField(max_length=100)
    physical_address = models.TextField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Staff(models.Model):
    """A facility staff member, linked to the platform's existing auth
    user model. Clinical roles carry a KMPDC number for verification."""

    class Role(models.TextChoices):
        DOCTOR = "doctor", "Doctor"
        NURSE = "nurse", "Nurse"
        LAB_TECH = "lab_tech", "Lab Technician"
        PHARMACIST = "pharmacist", "Pharmacist"
        CASHIER = "cashier", "Cashier"
        ADMIN = "admin", "Facility Admin"
        RECEPTIONIST = "receptionist", "Receptionist"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="staff")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hmis_staff_profiles",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    kmpdc_registration_number = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("facility", "user")

    def __str__(self):
        return f"{self.user} ({self.get_role_display()}) @ {self.facility.name}"


class Patient(models.Model):
    """Facility-scoped Master Patient Index entry. `patient_number` is the
    facility-assigned identifier shown on cards/labels. `national_id` is
    kept separate to support cross-facility patient matching later."""

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="patients")
    patient_number = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.UNKNOWN)
    national_id = models.CharField(max_length=20, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True)
    next_of_kin_name = models.CharField(max_length=200, blank=True)
    next_of_kin_phone = models.CharField(max_length=20, blank=True)

    # Each entry: {"substance": {"system": "...", "code": "...", "display": "Penicillin"},
    #              "reaction": "Rash", "severity": "moderate"}
    # Mirrors FHIR AllergyIntolerance shape for later export.
    allergies = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("facility", "patient_number")
        indexes = [
            models.Index(fields=["facility", "last_name", "first_name"]),
            models.Index(fields=["national_id"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.patient_number})"


class Encounter(models.Model):
    """A single interaction between a patient and the facility — the
    backbone record everything else (notes, diagnoses, invoices) attaches
    to. Maps directly to FHIR's Encounter resource."""

    class EncounterType(models.TextChoices):
        OUTPATIENT = "OPD", "Outpatient"
        INPATIENT = "IPD", "Inpatient"
        EMERGENCY = "ER", "Emergency"

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in-progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="encounters")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="encounters")
    encounter_type = models.CharField(max_length=10, choices=EncounterType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    attending_staff = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name="encounters"
    )
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    reason_for_visit = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["facility", "patient", "-start_datetime"]),
        ]

    def __str__(self):
        return f"{self.get_encounter_type_display()} - {self.patient} - {self.start_datetime:%Y-%m-%d}"


class ClinicalNote(models.Model):
    """Vitals, progress notes, and other clinical documentation tied to
    an Encounter. `structured_data` holds coded values (e.g. vitals as
    LOINC-coded key/value pairs) so it can later be exported as FHIR
    Observation resources without a schema change."""

    class NoteType(models.TextChoices):
        VITALS = "vitals", "Vital Signs"
        PROGRESS = "progress", "Progress Note"
        NURSING = "nursing", "Nursing Note"
        DISCHARGE_SUMMARY = "discharge_summary", "Discharge Summary"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="clinical_notes")
    author = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, related_name="authored_notes")
    note_type = models.CharField(max_length=30, choices=NoteType.choices)

    # Example for vitals:
    # [{"code": {"system": "http://loinc.org", "code": "8310-5", "display": "Body temperature"},
    #   "value": 37.2, "unit": "Cel"}, ...]
    structured_data = models.JSONField(default=dict, blank=True)
    free_text = models.TextField(blank=True)

    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.get_note_type_display()} - {self.encounter}"


class Diagnosis(models.Model):
    """A coded diagnosis tied to an Encounter. Stored in a FHIR
    Coding-shaped structure (system/code/display) rather than free text,
    so it maps directly to FHIR's Condition resource later."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="diagnoses")

    code_system = models.CharField(
        max_length=100,
        default="http://hl7.org/fhir/sid/icd-10",
        help_text="URI of the coding system, e.g. ICD-10.",
    )
    code = models.CharField(max_length=20, help_text="e.g. 'I10' for essential hypertension")
    display = models.CharField(max_length=255, help_text="Human-readable description of the code")

    is_primary = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, related_name="diagnoses_recorded"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "-recorded_at"]

    def __str__(self):
        return f"{self.code} - {self.display}"


class Invoice(models.Model):
    """A bill generated against an Encounter. `payer_type` distinguishes
    cash from SHA/insurance claims; `claim_reference` is populated once a
    claim is submitted (Phase 5 — SHA claims integration)."""

    class PayerType(models.TextChoices):
        CASH = "cash", "Cash"
        SHA = "sha", "SHA (Social Health Authority)"
        PRIVATE_INSURANCE = "private_insurance", "Private Insurance"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="invoices")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="invoices")
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="invoices")

    payer_type = models.CharField(max_length=20, choices=PayerType.choices, default=PayerType.CASH)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Each item: {"service_code": "CONS-001", "description": "Consultation",
    #             "quantity": 1, "unit_price": "1500.00"}
    line_items = models.JSONField(default=list)

    claim_reference = models.CharField(max_length=100, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def recalculate_total(self):
        """Call this after mutating line_items, before save()."""
        self.total_amount = sum(
            float(item.get("quantity", 1)) * float(item.get("unit_price", 0))
            for item in self.line_items
        )
        return self.total_amount

    def __str__(self):
        return f"Invoice {self.id} - {self.patient} - KES {self.total_amount}"


class Payment(models.Model):
    """A payment applied against an Invoice. Multiple payments can apply
    to one invoice (e.g. partial cash + insurance top-up)."""

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MPESA = "mpesa", "M-Pesa"
        BANK = "bank", "Bank Transfer"
        INSURANCE = "insurance", "Insurance"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    received_by = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, related_name="payments_received"
    )
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"KES {self.amount} - {self.method} - Invoice {self.invoice_id}"
