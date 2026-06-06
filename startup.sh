#!/bin/bash
set -e
echo "Running migrations..."
python manage.py migrate --no-input
echo "Starting server..."
gunicorn config.wsgi --bind 0.0.0.0:10000 --workers 1 --timeout 120
