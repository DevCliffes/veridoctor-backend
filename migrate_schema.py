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

    # healthcare provider account fixes — licence_number must allow NULL
    # so multiple providers without a licence on file don't collide on
    # a shared unique='' value, which was causing 500s on every signup
    # after the first.
    cursor.execute(
        "ALTER TABLE identity_healthcareprovideraccount ALTER COLUMN licence_number DROP NOT NULL;"
    )
    cursor.execute(
        "UPDATE identity_healthcareprovideraccount SET licence_number = NULL WHERE licence_number = '';"
    )

print("Schema updated successfully")
