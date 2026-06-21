#!/bin/bash
set -e
echo "Running schema updates..."
python migrate_schema.py
echo "Running migrations..."
python manage.py migrate --no-input
echo "Applying direct schema patches..."
python manage.py dbshell << 'SQL'
ALTER TABLE provider_service ALTER COLUMN price DROP NOT NULL;
SQL
echo "Backfilling patient record links..."
python manage.py backfill_patient_records
echo "Starting server..."
gunicorn config.wsgi --bind 0.0.0.0:10000 --workers 1 --timeout 120
