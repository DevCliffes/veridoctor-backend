import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0005_alter_appointmentcapture_form_snapshot_and_more"),
        (
            "notifications",
            "0002_rename_notifications_recipient_read_idx_notificatio_recipie_f533ae_idx",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                max_length=40,
                choices=[
                    ("appointment_booked", "Appointment booked"),
                    ("appointment_confirmed", "Appointment confirmed"),
                    ("appointment_cancelled", "Appointment cancelled"),
                    ("appointment_rescheduled", "Appointment rescheduled"),
                    ("appointment_reminder", "Appointment reminder"),
                    ("prescription_added", "Prescription added"),
                    ("prescription_ready", "Prescription ready"),
                    ("record_access_requested", "Record access requested"),
                    ("record_access_granted", "Record access granted"),
                ],
            ),
        ),
        migrations.CreateModel(
            name="AppointmentReminderLog",
            fields=[
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
                    "reminder_type",
                    models.CharField(
                        choices=[
                            ("24h", "24 hours before"),
                            ("3h", "3 hours before"),
                            ("10m", "10 minutes before"),
                        ],
                        max_length=10,
                    ),
                ),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                (
                    "appointment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reminder_logs",
                        to="appointments.providerappointment",
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_at"],
                "abstract": False,
            },
        ),
        migrations.AddConstraint(
            model_name="appointmentreminderlog",
            constraint=models.UniqueConstraint(
                fields=("appointment", "reminder_type"),
                name="unique_reminder_per_appointment_and_type",
            ),
        ),
    ]
