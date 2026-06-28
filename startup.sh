#!/bin/bash
set -e
echo "Running schema updates..."
python migrate_schema.py
echo "Running migrations..."
python manage.py migrate --no-input
echo "Marking notifications initial migration as already applied (one-time fix)..."
python manage.py migrate notifications 0001 --fake
echo "Backfilling patient record links..."
python manage.py backfill_patient_records
echo "Creating superuser..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@veridoctor.com').exists():
    User.objects.create_superuser('admin@veridoctor.com', 'Admin1234!')
"
echo "Collecting static files..."
python manage.py collectstatic --no-input
echo "Starting server..."
gunicorn config.wsgi --bind 0.0.0.0:10000 --workers 1 --timeout 120
