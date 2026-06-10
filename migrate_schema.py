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

print("Schema updated successfully")
