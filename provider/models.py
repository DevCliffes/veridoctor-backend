from django.db import models
import uuid
from identity.models import Identity

class HealthcareProvider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identity = models.OneToOneField(Identity, on_delete=models.CASCADE, related_name="provider_profile")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    licence_number = models.CharField(max_length=100, blank=True, null=True)
    licence_type = models.CharField(max_length=100, blank=True, null=True)
    speciality = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(HealthcareProvider, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=200)
    estimated_duration = models.IntegerField(help_text="Duration in minutes")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="KES")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
class Form(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(HealthcareProvider, on_delete=models.CASCADE, related_name="forms")
    name = models.CharField(max_length=200)
    sections = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
