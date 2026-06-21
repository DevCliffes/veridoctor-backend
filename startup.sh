#!/bin/bash
set -e
echo "Running schema updates..."
python migrate_schema.py
echo "Running migrations..."
python manage.py migrate --no-input
echo "Backfilling patient record links..."
python manage.py backfill_patient_records
echo "Starting server..."
gunicorn config.wsgi --bind 0.0.0.0:10000 --workers 1 --timeout 120
