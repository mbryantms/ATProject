import os

from celery import Celery

# Ensure Django settings are loaded for Celery workers
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ATProject.settings")

app = Celery("ATProject")

# Read settings with CELERY_ prefix from Django settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks.py in all INSTALLED_APPS
app.autodiscover_tasks()


# Optional: a simple debug task to verify wiring
@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
