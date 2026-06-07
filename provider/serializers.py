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
