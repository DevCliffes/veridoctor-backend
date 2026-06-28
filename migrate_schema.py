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
    # Check whether the legacy "name" column still exists before referencing it.
    # Earlier deploys may have already dropped it, or it may never have existed
    # under this exact name — querying information_schema avoids crashing the
    # whole boot sequence if either column is already gone.
    cursor.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'provider_prescriptiondrug' AND column_name = 'name';
        """
    )
    legacy_name_column_exists = cursor.fetchone() is not None

    if legacy_name_column_exists:
        cursor.execute(
            "UPDATE provider_prescriptiondrug SET drug_name = name WHERE drug_name = '' AND name IS NOT NULL;"
        )
        cursor.execute(
            "ALTER TABLE provider_prescriptiondrug DROP COLUMN IF EXISTS name;"
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

    # ── notifications_notification table ─────────────────────────────────────
    # Table already exists (created in a previous deploy via this script).
    # Ensure it exists, then fake the Django migration so manage.py migrate
    # doesn't try to CREATE TABLE again and error out.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications_notification (
            id uuid NOT NULL PRIMARY KEY,
            created_at timestamp with time zone NOT NULL,
            updated_at timestamp with time zone NOT NULL,
            recipient_identity_id uuid NOT NULL REFERENCES identity_identity(id) ON DELETE CASCADE,
            notification_type varchar(40) NOT NULL,
            title varchar(255) NOT NULL,
            message varchar(500) NOT NULL DEFAULT '',
            link varchar(255) NOT NULL DEFAULT '',
            is_read boolean NOT NULL DEFAULT false
        );
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS notifications_notification_recipient_identity_id_idx
        ON notifications_notification (recipient_identity_id);
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS notifications_notification_recipient_is_read_idx
        ON notifications_notification (recipient_identity_id, is_read);
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS notifications_notification_created_at_idx
        ON notifications_notification (created_at);
        """
    )

    # Fake the migration so Django doesn't try to CREATE TABLE again.
    # INSERT ... WHERE NOT EXISTS means this is safe to re-run on every deploy.
    cursor.execute(
        """
        INSERT INTO django_migrations (app, name, applied)
        SELECT 'notifications', '0001_initial', NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM django_migrations
            WHERE app = 'notifications' AND name = '0001_initial'
        );
        """
    )

print("Schema updated successfully")
