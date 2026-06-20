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

    # ── notifications_notification table ────────────────────────────────
    # The `notifications` app's model was never given a real Django
    # migration file (no local shell access to run makemigrations), so
    # `manage.py migrate` in startup.sh has nothing to apply for it and
    # the table was never created — every request to /notifications/
    # was 500-ing on a missing table. Created here directly, matching
    # exactly what Django would have generated from the model:
    #   - id: UUID primary key (BaseModel)
    #   - recipient_identity_id: UUID FK -> identity_identity.id
    #   - created_at / updated_at: BaseModel timestamps
    #   - notification_type / title / message / link / is_read: per model
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

print("Schema updated successfully")
