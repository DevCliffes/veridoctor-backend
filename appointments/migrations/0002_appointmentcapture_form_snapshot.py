import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appointments", "0001_initial"),
        ("provider", "0005_sync_provider_models"),
    ]

    operations = [
        # Step 1: Tell Django's migration state that AppointmentCapture exists,
        # and safely create it in the DB if it doesn't (IF NOT EXISTS).
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="AppointmentCapture",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("form_id", models.CharField(max_length=255)),
                        ("form_name", models.CharField(blank=True, max_length=255)),
                        ("form_snapshot", models.JSONField(blank=True, default=list)),
                        ("values", models.JSONField(default=dict)),
                        (
                            "appointment",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="captures",
                                to="appointments.providerappointment",
                            ),
                        ),
                    ],
                    options={"ordering": ["-created_at"]},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
CREATE TABLE IF NOT EXISTS appointments_appointmentcapture (
    id uuid NOT NULL PRIMARY KEY,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    form_id varchar(255) NOT NULL DEFAULT '',
    form_name varchar(255) NOT NULL DEFAULT '',
    values jsonb NOT NULL DEFAULT '{}'::jsonb,
    appointment_id uuid NOT NULL REFERENCES appointments_providerappointment(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS appointments_appointmentcapture_appointment_id_idx
    ON appointments_appointmentcapture (appointment_id);

ALTER TABLE appointments_appointmentcapture
    ADD COLUMN IF NOT EXISTS form_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
