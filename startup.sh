#!/bin/bash
set -e
echo "Running migrations..."
python manage.py migrate --no-input
echo "Starting server..."
python manage.py createsuperuser --noinput --username admin --email admin@veridoctor.com || true
gunicorn config.wsgi --bind 0.0.0.0:10000 --workers 1 --timeout 120
