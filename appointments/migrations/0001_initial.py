# Generated manually for the provider appointment API.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("provider", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProviderAppointment",
            fields=[
                (
                    "patient_first_name",
                    models.CharField(max_length=255),
                ),
                (
                    "patient_last_name",
                    models.CharField(max_length=255),
                ),
                ("patient_email", models.EmailField(blank=True, max_length=254)),
                ("patient_phone_number", models.CharField(blank=True, max_length=255)),
                ("start_time", models.DateTimeField()),
                ("end_time", models.DateTimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("scheduled", "Scheduled"),
                            ("confirmed", "Confirmed"),
                            ("in-progress", "In-progress"),
                            ("cancelled", "Cancelled"),
                            ("no-show", "No-show"),
                        ],
                        default="scheduled",
                        max_length=20,
                    ),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "appointment_type",
                    models.CharField(
                        choices=[("virtual", "Virtual"), ("physical", "Physical")],
                        default="virtual",
                        max_length=20,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("meet_id", models.CharField(blank=True, max_length=32, unique=True)),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appointments",
                        to="provider.healthcareprovider",
                    ),
                ),
            ],
            options={
                "ordering": ["start_time"],
            },
        ),
    ]
