from django.contrib import admin

from .models import ProviderAppointment


@admin.register(ProviderAppointment)
class ProviderAppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "patient_first_name",
        "patient_last_name",
        "appointment_type",
        "start_time",
        "status",
        "meet_id",
    )
    list_filter = ("appointment_type", "status")
    search_fields = ("patient_first_name", "patient_last_name", "patient_email", "meet_id")
