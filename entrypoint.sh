#!/bin/bash

BASE_COMMAND='python manage.py'
# 

# run migrations and collect static assets
$BASE_COMMAND migrate --noinput
$BASE_COMMAND collectstatic --noinput

# start the django server on prod WSGI server
exec "$@"