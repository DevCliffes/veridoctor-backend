import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    0003_patientrecordspin was deployed once with an earlier version of
    PatientRecordsPin (field `patient` -> settings.AUTH_USER_MODEL,
    BigAutoField id), which created the live table. The model/migration
    file content was later replaced (field `patient_identity`, UUID id)
    but Django tracks applied migrations by name only, so it never
    re-ran and the database never matched the current model.

    Table is empty (no PIN has ever been successfully set), so this
    drops and recreates it via the schema editor -- letting Django
    resolve the correct FK table/column names itself rather than us
    hardcoding them and risking another mismatch.
    """

    dependencies = [
        ("records", "0003_patientrecordspin"),
        ("identity", "0010_healthcareprovideraccount_subspecialties"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],  # model state is already correct as of 0003
            database_operations=[
                migrations.DeleteModel(name="PatientRecordsPin"),
                migrations.CreateModel(
                    name="PatientRecordsPin",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("pin_hash", models.CharField(max_length=128)),
                        ("failed_attempts", models.PositiveIntegerField(default=0)),
                        ("locked_until", models.DateTimeField(blank=True, null=True)),
                        (
                            "patient_identity",
                            models.OneToOneField(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="records_pin",
                                to="identity.identity",
                            ),
                        ),
                    ],
                ),
            ],
        ),
    ]
