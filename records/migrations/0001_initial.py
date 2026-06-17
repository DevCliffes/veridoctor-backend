import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("identity", "0007_authcode"),
        ("provider", "0006_fix_never_ending_schedules"),
    ]

    operations = [
        migrations.CreateModel(
            name="PatientProviderRecordSummary",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("record_count", models.PositiveIntegerField(default=0)),
                ("last_record_at", models.DateTimeField(blank=True, null=True)),
                ("sensitivity", models.CharField(
                    choices=[
                        ("always_visible", "Always visible to other providers"),
                        ("ask_first", "Ask patient before requesting"),
                        ("never", "Never visible to other providers"),
                    ],
                    default="ask_first",
                    max_length=20,
                )),
                ("patient_identity", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="record_summaries",
                    to="identity.identity",
                )),
                ("provider", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="patient_summaries",
                    to="provider.healthcareprovider",
                )),
            ],
            options={"ordering": ["-last_record_at"]},
        ),
        migrations.AlterUniqueTogether(
            name="patientproviderrecordsummary",
            unique_together={("patient_identity", "provider")},
        ),
    ]
