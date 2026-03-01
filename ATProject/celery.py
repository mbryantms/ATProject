import os

from celery import Celery
from celery.signals import task_postrun

# Ensure Django settings are loaded for Celery workers
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ATProject.settings")

app = Celery("ATProject")

# Read settings with CELERY_ prefix from Django settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks.py in all INSTALLED_APPS
# Use a callable to defer discovery until Django is ready
from django.conf import settings

app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@task_postrun.connect
def close_db_connections_after_task(**kwargs):
    """
    Force-close all DB connections after every Celery task.

    Django's built-in fixup calls close_old_connections(), which only closes
    connections older than CONN_MAX_AGE.  With CONN_MAX_AGE=0 that should
    suffice, but this handler guarantees connections are closed even if the
    setting is overridden via env var — critical for letting Neon auto-suspend.
    """
    from django import db

    db.connections.close_all()


# Optional: a simple debug task to verify wiring
@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
