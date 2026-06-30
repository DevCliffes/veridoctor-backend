from django.contrib import admin
from django.utils.html import format_html
from .models import Service, HealthcareProvider, Form, Prescription, PrescriptionDrug, ProviderSchedule


@admin.action(description="Recompute profile completeness for selected providers")
def recompute_profile_complete(modeladmin, request, queryset):
    for provider in queryset:
        provider.save()  # save() already recalculates profile_complete
    modeladmin.message_user(request, f"Recomputed {queryset.count()} provider(s).")


@admin.register(HealthcareProvider)
class HealthcareProviderAdmin(admin.ModelAdmin):
    list_display = ("__str__", "speciality", "county", "profile_complete_badge", "created_at")
    list_filter = ("profile_complete", "speciality", "county")
    search_fields = ("identity__first_name", "identity__last_name", "identity__email", "clinic_name")
    readonly_fields = ("missing_fields_display",)
    actions = [recompute_profile_complete]

    def profile_complete_badge(self, obj):
        if obj.profile_complete:
            return format_html('<span style="color: green;">✓ Complete</span>')
        return format_html(
            '<span style="color: #c0392b;">✗ Incomplete ({})</span>',
            len(obj.missing_fields()),
        )
    profile_complete_badge.short_description = "Profile status"

    def missing_fields_display(self, obj):
        missing = obj.missing_fields()
        if not missing:
            return "None — profile complete"
        return format_html("<br>".join(missing))
    missing_fields_display.short_description = "Missing fields"


admin.site.register(Service)
admin.site.register(Form)
admin.site.register(Prescription)
admin.site.register(PrescriptionDrug)
admin.site.register(ProviderSchedule)
