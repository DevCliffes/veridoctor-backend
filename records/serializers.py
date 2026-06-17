from rest_framework import serializers
from .models import PatientProviderRecordSummary


class PatientProviderRecordSummarySerializer(serializers.ModelSerializer):
    provider_first_name = serializers.CharField(
        source="provider.identity.first_name", read_only=True
    )
    provider_last_name = serializers.CharField(
        source="provider.identity.last_name", read_only=True
    )
    speciality = serializers.CharField(source="provider.speciality", read_only=True)
    clinic_name = serializers.CharField(source="provider.clinic_name", read_only=True)

    class Meta:
        model = PatientProviderRecordSummary
        fields = [
            "id",
            "provider",
            "provider_first_name",
            "provider_last_name",
            "speciality",
            "clinic_name",
            "record_count",
            "last_record_at",
            "sensitivity",
        ]
        read_only_fields = fields
