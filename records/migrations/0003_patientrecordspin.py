from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("records", "REPLACE_WITH_YOUR_LATEST_RECORDS_MIGRATION"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="PatientRecordsPin",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("pin_hash", models.CharField(max_length=128)),
                        ("failed_attempts", models.PositiveIntegerField(default=0)),
                        ("locked_until", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("patient", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="records_pin", to=settings.AUTH_USER_MODEL)),
                    ],
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS records_patientrecordspin (
                        id BIGSERIAL PRIMARY KEY,
                        pin_hash VARCHAR(128) NOT NULL,
                        failed_attempts INTEGER NOT NULL DEFAULT 0,
                        locked_until TIMESTAMP WITH TIME ZONE NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                        patient_id INTEGER NOT NULL UNIQUE REFERENCES REPLACE_WITH_YOUR_USER_TABLE(id) ON DELETE CASCADE
                    );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS records_patientrecordspin;",
                ),
            ],
        ),
    ]
