from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("provider", "0004_providerschedule_excluded_dates"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="title",
                    field=models.CharField(max_length=20, blank=True, null=True, default="Dr."),
                ),
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="clinic_name",
                    field=models.CharField(max_length=200, blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="address",
                    field=models.CharField(max_length=300, blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="county",
                    field=models.CharField(max_length=100, blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="country",
                    field=models.CharField(max_length=100, blank=True, null=True, default="Kenya"),
                ),
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="bio",
                    field=models.TextField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="insurances_accepted",
                    field=models.JSONField(default=list, blank=True),
                ),
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="languages",
                    field=models.JSONField(default=list, blank=True),
                ),
                migrations.AddField(
                    model_name="healthcareprovider",
                    name="profile_picture_url",
                    field=models.URLField(blank=True, null=True),
                ),
                migrations.CreateModel(
                    name="Prescription",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("patient_id", models.CharField(blank=True, max_length=255)),
                        ("patient_name", models.CharField(blank=True, max_length=255, null=True)),
                        ("patient_email", models.EmailField(blank=True, db_index=True, max_length=254, null=True)),
                        ("diagnosis", models.TextField(blank=True, null=True)),
                        ("notes", models.TextField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="prescriptions", to="provider.healthcareprovider")),
                    ],
                ),
                migrations.CreateModel(
                    name="PrescriptionDrug",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("drug_name", models.CharField(max_length=255)),
                        ("dosage", models.CharField(blank=True, max_length=100, null=True)),
                        ("frequency", models.CharField(max_length=100)),
                        ("duration", models.CharField(max_length=100)),
                        ("instructions", models.TextField(blank=True, null=True)),
                        ("prescription", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="drugs", to="provider.prescription")),
                    ],
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS title varchar(20) NULL DEFAULT 'Dr.';
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS clinic_name varchar(200) NULL;
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS address varchar(300) NULL;
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS county varchar(100) NULL;
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS country varchar(100) NULL DEFAULT 'Kenya';
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS bio text NULL;
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS insurances_accepted jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS languages jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS profile_picture_url varchar(200) NULL;

CREATE TABLE IF NOT EXISTS provider_prescription (
    id uuid NOT NULL PRIMARY KEY,
    patient_id varchar(255) NOT NULL DEFAULT '',
    patient_name varchar(255) NULL,
    patient_email varchar(254) NULL,
    diagnosis text NULL,
    notes text NULL,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    provider_id uuid NOT NULL REFERENCES provider_healthcareprovider(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS provider_prescription_patient_email_idx ON provider_prescription (patient_email);
CREATE INDEX IF NOT EXISTS provider_prescription_provider_id_idx ON provider_prescription (provider_id);

CREATE TABLE IF NOT EXISTS provider_prescriptiondrug (
    id uuid NOT NULL PRIMARY KEY,
    drug_name varchar(255) NOT NULL DEFAULT '',
    dosage varchar(100) NULL,
    frequency varchar(100) NOT NULL DEFAULT '',
    duration varchar(100) NOT NULL DEFAULT '',
    instructions text NULL,
    prescription_id uuid NOT NULL REFERENCES provider_prescription(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS provider_prescriptiondrug_prescription_id_idx ON provider_prescriptiondrug (prescription_id);
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
