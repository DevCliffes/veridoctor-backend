import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

with connection.cursor() as cursor:

    # ── prescription fixes ───────────────────────────────────────────────────
    cursor.execute(
        "ALTER TABLE provider_prescription ADD COLUMN IF NOT EXISTS patient_email varchar(254) NULL;"
    )
    cursor.execute(
        "ALTER TABLE provider_prescriptiondrug ADD COLUMN IF NOT EXISTS drug_name varchar(255) NOT NULL DEFAULT '';"
    )
    cursor.execute(
        "UPDATE provider_prescriptiondrug SET drug_name = name WHERE drug_name = '' AND name IS NOT NULL;"
    )

    # ── patientAccount missing columns ───────────────────────────────────────
    cursor.execute(
        "ALTER TABLE identity_patientaccount ADD COLUMN IF NOT EXISTS date_of_birth date NULL;"
    )
    cursor.execute(
        "ALTER TABLE identity_patientaccount ADD COLUMN IF NOT EXISTS blood_type varchar(10) NOT NULL DEFAULT 'UNKNOWN';"
    )
    cursor.execute(
        "ALTER TABLE identity_patientaccount ADD COLUMN IF NOT EXISTS allergies jsonb NOT NULL DEFAULT '[]';"
    )
    cursor.execute(
        "ALTER TABLE identity_patientaccount ADD COLUMN IF NOT EXISTS insurances jsonb NOT NULL DEFAULT '[]';"
    )

    # ── healthcare provider account fixes ────────────────────────────────────
    cursor.execute(
        "ALTER TABLE identity_healthcareprovideraccount ALTER COLUMN licence_number DROP NOT NULL;"
    )
    cursor.execute(
        "UPDATE identity_healthcareprovideraccount SET licence_number = NULL WHERE licence_number = '';"
    )

    # ── provider extended profile fields ─────────────────────────────────────
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS national_id_number varchar(50) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS national_id_image varchar(500) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS clinic_logo_url varchar(500) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS business_reg_number varchar(100) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS business_reg_image varchar(500) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS operating_licence varchar(100) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS operating_licence_image varchar(500) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS kra_pin varchar(50) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS kra_pin_image varchar(500) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS cr12_image varchar(500) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS valid_licence_number varchar(100) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS valid_licence_image varchar(500) NOT NULL DEFAULT '';")
    cursor.execute("ALTER TABLE provider_healthcareprovider ADD COLUMN IF NOT EXISTS extra_credentials jsonb NOT NULL DEFAULT '[]';")

    # ── provider_service.price must allow NULL ───────────────────────────────
    cursor.execute(
        "ALTER TABLE provider_service ALTER COLUMN price DROP NOT NULL;"
    )

print("Schema updated successfully")
