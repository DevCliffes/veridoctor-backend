import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "recipient_identity",
                    models.ForeignKey(
                        help_text="Who this notification is for — the provider or patient that should see it.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("appointment_booked", "Appointment booked"),
                            ("appointment_confirmed", "Appointment confirmed"),
                            ("appointment_cancelled", "Appointment cancelled"),
                            ("appointment_rescheduled", "Appointment rescheduled"),
                            ("prescription_added", "Prescription added"),
                            ("prescription_ready", "Prescription ready"),
                            ("record_access_requested", "Record access requested"),
                            ("record_access_granted", "Record access granted"),
                        ],
                        max_length=40,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("message", models.CharField(blank=True, max_length=500)),
                (
                    "link",
                    models.CharField(
                        blank=True,
                        help_text="Optional relative frontend path to navigate to when clicked, e.g. '/appointments/<id>'.",
                        max_length=255,
                    ),
                ),
                ("is_read", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["recipient_identity", "is_read"],
                name="notificatio_recipie_idx",
            ),
        ),
    ]
