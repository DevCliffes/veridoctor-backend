from .models import Service, HealthcareProvider, Form
from rest_framework import serializers
from .models import Service, HealthcareProvider


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
