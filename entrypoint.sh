#!/bin/bash

# run schema updates
python manage.py shell -c "
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('ALTER TABLE provider_prescription ADD COLUMN IF NOT EXISTS patient_email varchar(254) NULL;')
    cursor.execute('ALTER TABLE provider_prescriptiondrug ADD COLUMN IF NOT EXISTS drug_name varchar(255) NOT NULL DEFAULT \'\';')
    cursor.execute('UPDATE provider_prescriptiondrug SET drug_name = name WHERE drug_name = \'\';')
print('Schema updated successfully')
"

# run migrations and collect static assets  
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
