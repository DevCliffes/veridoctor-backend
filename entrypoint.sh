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
print('provider_form table ready')
"

# run migrations and collect static assets  
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
