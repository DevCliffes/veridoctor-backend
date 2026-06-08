#!/bin/bash
BASE_COMMAND='python manage.py'

# Create provider_form table directly if it doesn't exist
python manage.py shell -c "
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
"

# run migrations and collect static assets
$BASE_COMMAND migrate --noinput --fake-initial
$BASE_COMMAND collectstatic --noinput

# start the django server
exec "$@"
