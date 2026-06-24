#!/bin/bash
set -e
echo "Running schema updates..."
python migrate_schema.py
echo "Running migrations..."
python manage.py migrate --no-input
echo "Backfilling patient record links..."
python manage.py backfill_patient_records
echo "Starting server..."
#!/bin/bash
set -e
echo "Running schema updates..."
python migrate_schema.py
echo "Running migrations..."
python manage.py migrate --no-input
echo "Backfilling patient record links..."
python manage.py backfill_patient_records
echo "Creating superuser..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@veridoctor.com').exists():
    User.objects.create_superuser('admin@veridoctor.com', 'Admin1234!')
"
echo "Starting server..."
gunicorn config.wsgi --bind 0.0.0.0:10000 --workers 1 --timeout 120
