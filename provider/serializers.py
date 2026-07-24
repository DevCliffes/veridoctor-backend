from .models import (
    Service,
    HealthcareProvider,
    ProviderLocation,
    Form,
    Prescription,
    PrescriptionDrug,
    ProviderSchedule,
    ProviderReview,
    ProviderDocumentReview,
    ProviderLocationDocumentReview,
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


class ProviderLocationDocumentReviewSerializer(serializers.ModelSerializer):
    """Per-field review status for a single ProviderLocation's facility
    documents (clinic logo, business reg, operating licence, KRA PIN,
    CR12) — same shape as ProviderDocumentReviewSerializer, scoped to a
    location instead of the provider directly."""

    field_label = serializers.CharField(source="get_field_name_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    rejection_category_label = serializers.CharField(
        source="get_rejection_category_display", read_only=True
    )

    class Meta:
        model = ProviderLocationDocumentReview
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


class ProviderLocationSerializer(serializers.ModelSerializer):
    """Full read/write representation of one practice location, for the
    provider-facing "My Locations" UI. Includes nested document review
    statuses so the frontend can render a DocumentReviewBadge per field
    without an extra request per location.

    NOT for patient-facing use — this exposes business_reg_number,
    kra_pin, and raw document review detail. See
    ProviderLocationPublicSerializer for what patients should see."""

    document_reviews = ProviderLocationDocumentReviewSerializer(many=True, read_only=True)
    missing_fields = serializers.SerializerMethodField()

    class Meta:
        model = ProviderLocation
        fields = [
            "id",
            "name",
            "address",
            "county",
            "country",
            "clinic_logo_url",
            "business_reg_number",
            "business_reg_image",
            "operating_licence",
            "operating_licence_image",
            "kra_pin",
            "kra_pin_image",
            "cr12_image",
            "is_primary",
            "data_complete",
            "is_fully_approved_cache",
            "document_reviews",
            "missing_fields",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "data_complete",
            "is_fully_approved_cache",
            "document_reviews",
            "missing_fields",
            "created_at",
            "updated_at",
        ]

    def get_missing_fields(self, obj):
        return obj.missing_fields()


class ProviderLocationPublicSerializer(serializers.ModelSerializer):
    """What a patient is allowed to see about a provider's location:
    just enough to pick a facility when booking. Deliberately excludes
    business_reg_number, kra_pin, document URLs, and review status —
    none of that is patient-facing information.

    Also reused (read-only, via `location_detail`) on
    ProviderScheduleSerializer below, since a provider's own schedule
    UI needs the same "just enough to identify the place" shape and
    there's no reason to duplicate it."""

    class Meta:
        model = ProviderLocation
        fields = ["id", "name", "address", "county", "country", "is_primary"]
        read_only_fields = fields


class ProviderScheduleSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True, default=None)
    # Read-only nested detail so the schedule UI can render a location's
    # name/address without a second request per block. `location` itself
    # stays a plain PK field for writes.
    location_detail = ProviderLocationPublicSerializer(source="location", read_only=True)

    class Meta:
        model = ProviderSchedule
        fields = [
            "id",
            "service",
            "service_name",
            "location",
            "location_detail",
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

    def validate(self, attrs):
        # On a PATCH, an untouched field won't be in attrs -- fall back to
        # the existing instance value so a partial update to e.g. just
        # start_time doesn't false-positive as "location_type changed to
        # physical with no location".
        location_type = attrs.get(
            "location_type",
            getattr(self.instance, "location_type", None),
        )
        location = attrs.get(
            "location",
            getattr(self.instance, "location", None) if self.instance else None,
        )

        if location_type in ("physical", "both") and not location:
            raise serializers.ValidationError(
                {"location": "Select a practice location for an in-person or hybrid schedule block."}
            )

        if location_type == "virtual" and location:
            # Virtual blocks are location-less by design (confirmed
            # deliberately, not an oversight) -- the frontend picker is
            # hidden for virtual, so this only guards against a stale
            # location value slipping through on an edit that switches
            # physical/both -> virtual without clearing it client-side.
            attrs["location"] = None

        return attrs

    def validate_location(self, value):
        # Guards against a provider (or a raw API call) attaching a
        # location that belongs to a different provider entirely.
        # `self.instance.provider` covers PATCH; `self.context["provider"]`
        # covers POST, where the view passes it in explicitly since the
        # serializer has no provider yet on create.
        if value is None:
            return value
        provider = (
            self.instance.provider if self.instance else self.context.get("provider")
        )
        if provider is not None and value.provider_id != provider.id:
            raise serializers.ValidationError("This location doesn't belong to you.")
        return value


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
    """Read-only view of a provider's per-document review status
    (national ID, valid licence — the two personal/professional docs
    that still live on HealthcareProvider itself)."""

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
