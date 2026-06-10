#!/bin/bash

# Run schema updates
python migrate_schema.py

# Run migrations and collect static assets  
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
