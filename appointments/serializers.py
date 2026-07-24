from rest_framework import serializers
from .models import ProviderAppointment, AppointmentCapture
from provider.serializers import ProviderLocationPublicSerializer


class ProviderAppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()
    service_name = serializers.CharField(
        source="service.name", read_only=True, default=None
    )
    provider_first_name = serializers.SerializerMethodField()
    provider_last_name = serializers.SerializerMethodField()
    provider_id = serializers.SerializerMethodField()
    # Read-only nested detail so appointment lists/detail views can show
    # which facility a physical visit is at without a second request.
    # `location` itself stays a plain PK field for writes -- same split
    # as ProviderScheduleSerializer.location / location_detail.
    location_detail = ProviderLocationPublicSerializer(source="location", read_only=True)

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
            "provider_id",
            "appointment_type",
            "location",
            "location_detail",
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

    def get_provider_id(self, appointment):
        try:
            return str(appointment.provider.identity.id)
        except Exception:
            return None

    def validate(self, attrs):
        # On a PATCH (status updates, reschedules, etc.), an untouched
        # field won't be in attrs -- fall back to the existing instance
        # value so e.g. a status-only PATCH doesn't false-positive as
        # "appointment_type changed to physical with no location".
        appointment_type = attrs.get(
            "appointment_type",
            getattr(self.instance, "appointment_type", None),
        )
        location = attrs.get(
            "location",
            getattr(self.instance, "location", None) if self.instance else None,
        )

        if appointment_type == "physical" and not location:
            raise serializers.ValidationError(
                {"location": "Select which of the provider's locations this appointment is at."}
            )

        if appointment_type == "virtual" and location:
            # Virtual appointments are location-less by design -- guards
            # against a stale location value slipping through on an edit
            # that switches physical -> virtual without clearing it
            # client-side.
            attrs["location"] = None

        return attrs

    def validate_location(self, value):
        # Guards against a location that belongs to a different provider
        # entirely being attached to this appointment. `self.instance.
        # provider` covers PATCH; `self.context["provider"]` covers
        # create, where the view passes it in explicitly since the
        # serializer has no provider yet on POST (provider isn't even a
        # serializer field -- it's set via .save(provider=provider) in
        # the view).
        if value is None:
            return value
        provider = (
            self.instance.provider if self.instance else self.context.get("provider")
        )
        if provider is not None and value.provider_id != provider.id:
            raise serializers.ValidationError(
                "This location doesn't belong to the selected provider."
            )
        return value


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
