# Process types for Railway multi-service deployment
# Create separate Railway services and override the start command per service

# Web server (configured in railway.toml startCommand)
web: gunicorn ATProject.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100

# Celery worker - create separate Railway service with this start command
worker: celery -A ATProject worker --loglevel=info --concurrency=2

# Celery beat scheduler - create separate Railway service with this start command
beat: celery -A ATProject beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
