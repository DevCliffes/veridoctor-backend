from rest_framework import serializers
from .models import Service, HealthcareProvider, Form, Prescription, PrescriptionDrug


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
        fields = ["id", "name", "dosage", "frequency", "duration", "instructions"]


class PrescriptionSerializer(serializers.ModelSerializer):
    drugs = PrescriptionDrugSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "patient_id",
            "patient_name",
            "diagnosis",
            "notes",
            "drugs",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
