# PRODUCTION DOCKER BUILD
FROM python:3.12-slim AS builder

# Set environment variables to reduce Python output and avoid .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

# setting env variables
WORKDIR /app

# installing dependencies
RUN pip install --no-cache-dir poetry==2.2.1

COPY poetry.lock pyproject.toml /app/

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root --only main

# Application files
COPY . .

# stage 2
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# setting working directoey
WORKDIR /app

# copying installed python dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user for security
RUN groupadd -r django && useradd -r -g django django \
    && chown -R django:django /app

# Copying app files
COPY --chown=django:django . .

# Copy entrypoint script
COPY --chown=django:django entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Switch to non-root user
USER django
# TODO: add healthchecks
# create the static files directory
RUN mkdir -p /app/staticfiles

ENTRYPOINT [ "/app/entrypoint.sh"]

CMD ["gunicorn", "-c", "gunicorn.conf.py", "config.wsgi"]
