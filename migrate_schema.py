import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute(
        "ALTER TABLE provider_prescription ADD COLUMN IF NOT EXISTS patient_email varchar(254) NULL;"
    )
    cursor.execute(
        "ALTER TABLE provider_prescriptiondrug ADD COLUMN IF NOT EXISTS drug_name varchar(255) NOT NULL DEFAULT '';"
    )
    cursor.execute(
        "UPDATE provider_prescriptiondrug SET drug_name = name WHERE drug_name = '' AND name IS NOT NULL;"
    )

    # patientAccount missing columns
    cursor.execute(
        "ALTER TABLE identity_patientaccount ADD COLUMN IF NOT EXISTS date_of_birth date NULL;"
    )
    cursor.execute(
        "ALTER TABLE identity_patientaccount ADD COLUMN IF NOT EXISTS blood_type varchar(10) NOT NULL DEFAULT 'UNKNOWN';"
    )
    cursor.execute(
        "ALTER TABLE identity_patientaccount ADD COLUMN IF NOT EXISTS allergies jsonb NOT NULL DEFAULT '[]';"
    )

    # patient_uid column — add as nullable first (existing rows have no value yet)
    cursor.execute(
        "ALTER TABLE identity_patientaccount ADD COLUMN IF NOT EXISTS patient_uid varchar(20) NULL;"
    )
    # backfill any existing rows that don't have a uid yet, using their row id as a seed
    cursor.execute(
        """
        UPDATE identity_patientaccount
        SET patient_uid = 'VD-' || LPAD((FLOOR(RANDOM() * 99999))::text, 5, '0')
        WHERE patient_uid IS NULL;
        """
    )
    # now add the unique constraint, only if it doesn't already exist
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'identity_patientaccount_patient_uid_key'
            ) THEN
                ALTER TABLE identity_patientaccount ADD CONSTRAINT identity_patientaccount_patient_uid_key UNIQUE (patient_uid);
            END IF;
        END $$;
        """
    )

print("Schema updated successfully")
