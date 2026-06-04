from django.contrib import admin
from .models import Facility, Workstation
from unfold import admin as unfold_admin


@admin.register(Facility)
class FacilityAdmin(unfold_admin.ModelAdmin):
    list_display = [field.name for field in Facility._meta.fields]
    search_fields = ["name", "location"]
    filter_horizontal = ("managers",)


@admin.register(Workstation)
class WorkstationAdmin(unfold_admin.ModelAdmin):
    list_display = [field.name for field in Workstation._meta.fields]
    search_fields = ["name"]
