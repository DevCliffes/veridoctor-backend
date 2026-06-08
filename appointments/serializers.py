from rest_framework import serializers

from .models import ProviderAppointment


class ProviderAppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()

    class Meta:
        model = ProviderAppointment
        fields = [
            "id",
            "patient_first_name",
            "patient_last_name",
            "patient_name",
            "patient_email",
            "patient_phone_number",
            "appointment_type",
            "message",
            "start_time",
            "end_time",
            "status",
            "meet_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "meet_id", "created_at", "updated_at"]

    def get_patient_name(self, appointment):
        return (
            f"{appointment.patient_first_name} {appointment.patient_last_name}".strip()
        )

