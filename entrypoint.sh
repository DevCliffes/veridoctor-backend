#!/bin/bash

# Create provider_form table directly if it doesn't exist
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS provider_form (
            id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
            name varchar(200) NOT NULL,
            sections jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            provider_id uuid NOT NULL REFERENCES provider_healthcareprovider(id) ON DELETE CASCADE
        );
    ''')
    
    # Add patient_email column if it doesn't exist
    cursor.execute('''
        ALTER TABLE provider_prescription 
        ADD COLUMN IF NOT EXISTS patient_email varchar(254) NULL;
    ''')
    
    # Add drug_name column if it doesn't exist (renamed from name)
    cursor.execute('''
        ALTER TABLE provider_prescriptiondrug 
        ADD COLUMN IF NOT EXISTS drug_name varchar(255) NOT NULL DEFAULT '';
    ''')
    
    # Copy existing name values into drug_name if name column exists
    cursor.execute('''
        DO \$\$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'provider_prescriptiondrug' AND column_name = 'name'
            ) THEN
                UPDATE provider_prescriptiondrug SET drug_name = name WHERE drug_name = '';
            END IF;
        END \$\$;
    ''')

print('Database schema updated')
"

# run migrations and collect static assets  
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
