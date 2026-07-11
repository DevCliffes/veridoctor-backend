from django.contrib import admin
from . import models


@admin.register(models.PatientRecordAccessLog)
class PatientRecordAccessLogAdmin(admin.ModelAdmin):
    """Read-only: this is an audit trail, not editable data."""
    list_display = ("patient", "accessed_by", "action", "resource", "accessed_at")
    list_filter = ("action",)
    readonly_fields = [f.name for f in models.PatientRecordAccessLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = ("patient", "facility", "encounter_type", "status", "scheduled_at")
    list_filter = ("status", "encounter_type", "facility")
    search_fields = ("patient__patient_uid",)


@admin.register(models.ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    list_display = ("encounter", "author", "note_type", "is_signed", "signed_at")
    list_filter = ("note_type", "is_signed")

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_signed:
            return [f.name for f in obj._meta.fields]
        return []

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.is_signed)


@admin.register(models.LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display = ("id", "lab_order", "is_abnormal", "result_file", "resulted_at")
    list_filter = ("is_abnormal",)


admin.site.register(models.VitalSigns)
admin.site.register(models.ClinicalNoteAddendum)
admin.site.register(models.Diagnosis)
admin.site.register(models.MedicationOrder)
admin.site.register(models.LabOrder)
admin.site.register(models.Invoice)
admin.site.register(models.InvoiceLineItem)
admin.site.register(models.Payment)
admin.site.register(models.ConsentRecord)
