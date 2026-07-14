from .models import (
    Service,
    HealthcareProvider,
    Form,
    Prescription,
    PrescriptionDrug,
    ProviderSchedule,
    ProviderReview,
    ProviderDocumentReview,
)
from rest_framework import serializers
class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "estimated_duration",
            "price",
            "currency",
            "description",
            "price_visible",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
class FormSerializer(serializers.ModelSerializer):
    class Meta:
        model = Form
        fields = ["id", "name", "sections", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
class PrescriptionDrugSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionDrug
        fields = ["id", "drug_name", "dosage", "frequency", "duration", "instructions"]
        read_only_fields = ["id"]
class PrescriptionSerializer(serializers.ModelSerializer):
    drugs = PrescriptionDrugSerializer(many=True, read_only=True)
    provider = serializers.SerializerMethodField()
    class Meta:
        model = Prescription
        fields = [
            "id",
            "patient_id",
            "patient_name",
            "patient_email",
            "patient_identity",
            "diagnosis",
            "notes",
            "drugs",
            "provider",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "patient_identity", "created_at", "updated_at"]
    def get_provider(self, obj):
        identity = obj.provider.identity
        return {
            "first_name": getattr(identity, "first_name", ""),
            "last_name": getattr(identity, "last_name", ""),
            "speciality": obj.provider.speciality,
        }
class ProviderScheduleSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True, default=None)
    class Meta:
        model = ProviderSchedule
        fields = [
            "id",
            "service",
            "service_name",
            "location_type",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "recurrence",
            "recurrence_interval",
            "recurrence_days",
            "recurrence_end_type",
            "recurrence_end_date",
            "recurrence_count",
            "excluded_dates",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
class ProviderReviewPublicSerializer(serializers.ModelSerializer):
    """Public-facing serializer — deliberately excludes patient_last_name,
    patient_identity, and appointment. Only first name, rating, comment,
    and date are ever exposed."""
    class Meta:
        model = ProviderReview
        fields = ["id", "patient_first_name", "rating", "comment", "created_at"]
        read_only_fields = fields
class ProviderReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderReview
        fields = ["id", "provider", "appointment", "rating", "comment", "created_at"]
        read_only_fields = ["id", "provider", "created_at"]
    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value


class ProviderDocumentReviewSerializer(serializers.ModelSerializer):
    """Read-only view of a provider's per-document review status, used by
    ProviderDocumentReviewListView so providers can see exactly what was
    rejected and why (category + free-text reason) and re-upload
    accordingly."""

    field_label = serializers.CharField(source="get_field_name_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    rejection_category_label = serializers.CharField(
        source="get_rejection_category_display", read_only=True
    )

    class Meta:
        model = ProviderDocumentReview
        fields = [
            "field_name",
            "field_label",
            "status",
            "status_label",
            "document_url",
            "rejection_category",
            "rejection_category_label",
            "rejection_reason",
            "reviewed_at",
        ]
        read_only_fields = fields
