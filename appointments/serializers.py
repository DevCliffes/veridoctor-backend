from rest_framework import serializers
from .models import ProviderAppointment, AppointmentCapture


class ProviderAppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()
    service_name = serializers.CharField(
        source="service.name", read_only=True, default=None
    )
    provider_first_name = serializers.SerializerMethodField()
    provider_last_name = serializers.SerializerMethodField()

    class Meta:
        model = ProviderAppointment
        fields = [
            "id",
            "patient_first_name",
            "patient_last_name",
            "patient_name",
            "patient_email",
            "patient_phone_number",
            "patient_identity",
            "provider_first_name",
            "provider_last_name",
            "appointment_type",
            "service",
            "service_name",
            "message",
            "start_time",
            "end_time",
            "status",
            "meet_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "patient_identity", "meet_id", "created_at", "updated_at"]

    def get_patient_name(self, appointment):
        return f"{appointment.patient_first_name} {appointment.patient_last_name}".strip()

    def get_provider_first_name(self, appointment):
        try:
            return appointment.provider.identity.first_name
        except Exception:
            return None

    def get_provider_last_name(self, appointment):
        try:
            return appointment.provider.identity.last_name
        except Exception:
            return None


class AppointmentCaptureSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppointmentCapture
        fields = [
            "id",
            "appointment",
            "form_id",
            "form_name",
            "form_snapshot",
            "values",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "appointment", "created_at", "updated_at"]
