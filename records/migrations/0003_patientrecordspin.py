import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0010_healthcareprovideraccount_subspecialties"),
        ("records", "0002_recordaccessgrant"),
    ]

    operations = [
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
            options={"abstract": False},
        ),
    ]
