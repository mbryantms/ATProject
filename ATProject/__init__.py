# Expose the Celery app as "celery_app" to keep import paths short
from .celery import app as celery_app

__all__ = ("celery_app",)
