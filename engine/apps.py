from django.apps import AppConfig


class EngineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "engine"

    def ready(self):
        """Import signal handlers when app is ready."""
        import engine.signals  # noqa: F401 - Register post signal handlers
        import engine.utils  # noqa: F401 - Register asset signal handlers
