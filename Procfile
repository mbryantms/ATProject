# Process types for Railway multi-service deployment
# Create separate Railway services and set the start command to the process type
# e.g., for worker service, set start command to: celery -A ATProject worker...

# Web server (default - also configured in railway.toml)
web: gunicorn ATProject.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100

# Celery worker - deploy as separate Railway service
worker: celery -A ATProject worker --loglevel=info --concurrency=2

# Celery beat scheduler - deploy as separate Railway service
beat: celery -A ATProject beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
