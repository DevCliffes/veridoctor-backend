from django.contrib import admin
from .models import Identity, Otp, patientAccount, FacilityManagerAccount, BranchManagerAccount, HealthcareProviderAccount
from unfold import admin as unfold_admin

@admin.register(Identity)
class IdentityAdmin(unfold_admin.ModelAdmin):
    list_display = [field.name for field in Identity._meta.fields if field.name != 'password']
    search_fields = ['email', 'first_name', 'last_name']


@admin.register(Otp)
class OtpAdmin(unfold_admin.ModelAdmin):
    list_display = [field.name for field in Otp._meta.fields]

@admin.register(patientAccount)
class PatientAccountAdmin(unfold_admin.ModelAdmin):
    list_display = [field.name for field in patientAccount._meta.fields]
    search_fields = ['identity__email', 'identity__first_name', 'identity__last_name']

@admin.register(FacilityManagerAccount)
class FacilityManagerAccountAdmin(unfold_admin.ModelAdmin):
    list_display = [field.name for field in FacilityManagerAccount._meta.fields]
    search_fields = ['identity__email', 'identity__first_name', 'identity__last_name']

@admin.register(BranchManagerAccount)
class BranchManagerAccountAdmin(unfold_admin.ModelAdmin):
    list_display = [field.name for field in BranchManagerAccount._meta.fields]
    search_fields = ['identity__email', 'identity__first_name', 'identity__last_name']

@admin.register(HealthcareProviderAccount)
class HealthcareProviderAccountAdmin(unfold_admin.ModelAdmin):
    list_display = [field.name for field in HealthcareProviderAccount._meta.fields]
    search_fields = ['identity__email', 'identity__first_name', 'identity__last_name']