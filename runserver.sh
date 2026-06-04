#!/bin/bash

BASE_COMMAND='poetry run python manage.py'
# 

$BASE_COMMAND migrate
$BASE_COMMAND collectstatic --noinput
$BASE_COMMAND runserver 0.0.0.0:8000
