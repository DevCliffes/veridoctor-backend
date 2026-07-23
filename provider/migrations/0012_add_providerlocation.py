import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("provider", "0011_providerreview"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProviderLocation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(blank=True, default="", max_length=200)),
                ("address", models.CharField(blank=True, default="", max_length=300)),
                ("county", models.CharField(blank=True, default="", max_length=100)),
                ("country", models.CharField(blank=True, default="Kenya", max_length=100)),
                ("clinic_logo_url", models.CharField(blank=True, default="", max_length=500)),
                ("business_reg_number", models.CharField(blank=True, default="", max_length=100)),
                ("business_reg_image", models.CharField(blank=True, default="", max_length=500)),
                ("operating_licence", models.CharField(blank=True, default="", max_length=100)),
                ("operating_licence_image", models.CharField(blank=True, default="", max_length=500)),
                ("kra_pin", models.CharField(blank=True, default="", max_length=50)),
                ("kra_pin_image", models.CharField(blank=True, default="", max_length=500)),
                ("cr12_image", models.CharField(blank=True, default="", max_length=500)),
                (
                    "is_primary",
                    models.BooleanField(
                        default=False,
                        help_text="The location backfilled from this provider's original single-facility "
                        "data, or otherwise designated as their main/default location.",
                    ),
                ),
                ("data_complete", models.BooleanField(default=False)),
                (
                    "is_fully_approved_cache",
                    models.BooleanField(
                        default=False,
                        help_text="Denormalized copy of is_fully_approved, kept in sync on save() "
                        "and whenever a ProviderLocationDocumentReview changes, so "
                        "HealthcareProvider.is_bookable can filter on it directly "
                        "instead of evaluating a Python property per row.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="locations",
                        to="provider.healthcareprovider",
                    ),
                ),
            ],
            options={
                "ordering": ["-is_primary", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="ProviderLocationDocumentReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "field_name",
                    models.CharField(
                        choices=[
                            ("clinic_logo_url", "Clinic Logo"),
                            ("business_reg_image", "Business Registration"),
                            ("operating_licence_image", "Operating Licence"),
                            ("kra_pin_image", "KRA PIN"),
                            ("cr12_image", "CR12"),
                        ],
                        max_length=64,
                    ),
                ),
                ("document_url", models.URLField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "rejection_category",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("incorrect", "Incorrect document (wrong type / doesn't match provider)"),
                            ("unclear", "Unclear (blurry, cropped, low resolution, glare)"),
                            ("incomplete", "Incomplete (missing pages, expired, partial info)"),
                            ("other", "Other"),
                        ],
                        default="",
                        max_length=16,
                    ),
                ),
                ("rejection_reason", models.TextField(blank=True, default="")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_reviews",
                        to="provider.providerlocation",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["location", "field_name"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="providerlocationdocumentreview",
            unique_together={("location", "field_name")},
        ),
    ]
