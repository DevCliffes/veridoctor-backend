from rest_framework import serializers
from . import models


class VitalSignsSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.VitalSigns
        fields = "__all__"
        read_only_fields = ["recorded_by", "recorded_at"]


class ClinicalNoteAddendumSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ClinicalNoteAddendum
        fields = "__all__"
        read_only_fields = ["author"]


class ClinicalNoteSerializer(serializers.ModelSerializer):
    addenda = ClinicalNoteAddendumSerializer(many=True, read_only=True)

    class Meta:
        model = models.ClinicalNote
        fields = "__all__"
        read_only_fields = ["author", "is_signed", "signed_at"]

    def update(self, instance, validated_data):
        if instance.is_signed:
            raise serializers.ValidationError(
                "This note is signed and immutable. Submit a ClinicalNoteAddendum instead."
            )
        return super().update(instance, validated_data)


class DiagnosisSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Diagnosis
        fields = "__all__"
        read_only_fields = ["diagnosed_by", "diagnosed_at"]


class MedicationOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MedicationOrder
        fields = "__all__"
        read_only_fields = ["prescribed_by", "prescribed_at"]


class LabResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LabResult
        fields = "__all__"
        read_only_fields = ["resulted_at"]


class LabOrderSerializer(serializers.ModelSerializer):
    result = LabResultSerializer(read_only=True)

    class Meta:
        model = models.LabOrder
        fields = "__all__"
        read_only_fields = ["ordered_by", "ordered_at"]


class EncounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Encounter
        fields = "__all__"
        read_only_fields = ["closed_by"]


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    line_total = serializers.ReadOnlyField()

    class Meta:
        model = models.InvoiceLineItem
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Payment
        fields = "__all__"
        read_only_fields = ["received_by", "paid_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    line_items = InvoiceLineItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    total_amount = serializers.ReadOnlyField()
    amount_paid = serializers.ReadOnlyField()
    balance_due = serializers.ReadOnlyField()

    class Meta:
        model = models.Invoice
        fields = "__all__"


class ConsentRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ConsentRecord
        fields = "__all__"
        read_only_fields = ["granted_at", "revoked_at", "witnessed_by"]


class PatientRecordAccessLogSerializer(serializers.ModelSerializer):
    """Read-only by design — this is the audit trail, never written to via the API directly."""

    class Meta:
        model = models.PatientRecordAccessLog
        fields = "__all__"
        read_only_fields = fields
