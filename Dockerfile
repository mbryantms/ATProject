# syntax=docker/dockerfile:1
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files (uses dummy values for required env vars during build)
RUN SECRET_KEY=build-placeholder \
    DATABASE_URL=postgres://placeholder:placeholder@placeholder:5432/placeholder \
    REDIS_URL=redis://placeholder:6379 \
    python manage.py collectstatic --noinput

# Railway uses dynamic PORT env var
ENV PORT=8000
EXPOSE $PORT

# Run migrations then start gunicorn (shell form to expand $PORT)
# The -c flag loads gunicorn.conf.py which includes post_fork hooks
# to close inherited DB connections — critical for Neon auto-suspend.
CMD python manage.py migrate --noinput && gunicorn -c gunicorn.conf.py ATProject.wsgi:application
