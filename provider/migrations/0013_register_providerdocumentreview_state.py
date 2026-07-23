import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    ProviderDocumentReview already exists as a real table in the database
    (used throughout admin.py, with real review data in it), but no
    migration in this app's history ever created it -- so Django's
    migration state doesn't know it exists, even though the DB does.

    This migration fixes that mismatch WITHOUT touching the database:
    state_operations teaches Django's migration graph about the model,
    database_operations is empty so nothing is actually executed against
    Postgres (the table is untouched, no risk of clobbering existing
    data or hitting a "relation already exists" error).

    Field definitions below match the model as it existed just before
    the ProviderLocation split (7-item DOCUMENT_FIELD_CHOICES, including
    the 5 facility fields that migration 0015 removes from the choices
    list later). This is deliberate -- it should describe what's
    actually in the database *right now*, not the end state.
    """

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("provider", "0012_add_providerlocation"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="ProviderDocumentReview",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                            ),
                        ),
                        (
                            "field_name",
                            models.CharField(
                                choices=[
                                    ("national_id_image", "National ID"),
                                    ("clinic_logo_url", "Clinic Logo"),
                                    ("business_reg_image", "Business Registration"),
                                    ("operating_licence_image", "Operating Licence"),
                                    ("kra_pin_image", "KRA PIN"),
                                    ("cr12_image", "CR12"),
                                    ("valid_licence_image", "Valid Licence"),
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
                            "provider",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="document_reviews",
                                to="provider.healthcareprovider",
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
                        "ordering": ["provider", "field_name"],
                    },
                ),
                migrations.AlterUniqueTogether(
                    name="providerdocumentreview",
                    unique_together={("provider", "field_name")},
                ),
            ],
        ),
    ]
