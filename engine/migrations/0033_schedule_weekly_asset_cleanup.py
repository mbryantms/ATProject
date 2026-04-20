"""Seed a weekly cleanup schedule for orphaned assets via django-celery-beat.

Idempotent: re-applying the migration won't create duplicate schedules.
"""

import json

from django.db import migrations

TASK_NAME = "engine.tasks.cleanup_orphaned_assets"
PERIODIC_TASK_NAME = "Weekly asset cleanup (orphaned renditions + unused assets)"
CRONTAB = {
    "minute": "0",
    "hour": "3",
    "day_of_week": "0",
    "day_of_month": "*",
    "month_of_year": "*",
    "timezone": "UTC",
}
TASK_KWARGS = {
    "delete_files": True,
    "days_old": 30,
    "cleanup_renditions": True,
    "cleanup_unused": True,
}


def create_schedule(apps, schema_editor):
    try:
        CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
        PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    except LookupError:
        return

    schedule, _ = CrontabSchedule.objects.get_or_create(**CRONTAB)
    PeriodicTask.objects.get_or_create(
        name=PERIODIC_TASK_NAME,
        defaults={
            "task": TASK_NAME,
            "crontab": schedule,
            "kwargs": json.dumps(TASK_KWARGS),
            "enabled": True,
            "description": (
                "Runs weekly. Deletes orphaned renditions and unused "
                "soft-deleted assets older than 30 days (R2 files + DB rows)."
            ),
        },
    )


def remove_schedule(apps, schema_editor):
    try:
        PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    except LookupError:
        return
    PeriodicTask.objects.filter(name=PERIODIC_TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("engine", "0032_alter_assetrendition_status"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
