# Procfile - Process definitions for Railway deployment
# Each line defines a separate service that can be deployed independently
# https://docs.railway.app/guides/Procfiles

# Web server - Django application served via Gunicorn
web: gunicorn ATProject.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100

# Celery worker - Background task processing
worker: celery -A ATProject worker --loglevel=info --concurrency=2

# Celery beat - Scheduled task scheduler
beat: celery -A ATProject beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

# Release command - Runs after build, before deploy (migrations)
release: python manage.py migrate --noinput
