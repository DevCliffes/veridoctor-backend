from django.contrib import admin

from .models import (
    ClinicalNote,
    Diagnosis,
    Encounter,
    Facility,
    Invoice,
    Patient,
    Payment,
    Staff,
)


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "county", "kmpdc_facility_code", "sha_facility_code", "is_active")
    search_fields = ("name", "kmpdc_facility_code", "sha_facility_code")
    list_filter = ("county", "is_active")


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("user", "facility", "role", "kmpdc_registration_number", "is_active")
    list_filter = ("facility", "role", "is_active")
    search_fields = ("user__email", "kmpdc_registration_number")


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("patient_number", "first_name", "last_name", "facility", "gender", "phone_number")
    list_filter = ("facility", "gender")
    search_fields = ("patient_number", "first_name", "last_name", "national_id", "phone_number")


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = ("patient", "facility", "encounter_type", "status", "start_datetime", "attending_staff")
    list_filter = ("facility", "encounter_type", "status")
    search_fields = ("patient__first_name", "patient__last_name", "patient__patient_number")
    date_hierarchy = "start_datetime"


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    list_display = ("encounter", "note_type", "author", "recorded_at")
    list_filter = ("note_type",)


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ("encounter", "code", "display", "is_primary", "recorded_at")
    list_filter = ("is_primary", "code_system")
    search_fields = ("code", "display")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "facility", "payer_type", "status", "total_amount", "created_at")
    list_filter = ("facility", "payer_type", "status")
    search_fields = ("patient__first_name", "patient__last_name", "claim_reference")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "method", "reference_number", "received_by", "paid_at")
    list_filter = ("method",)
