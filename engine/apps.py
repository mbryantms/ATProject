from django.apps import AppConfig


class EngineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "engine"

    def ready(self):
        """Import signal handlers when app is ready."""
        import engine.signals  # noqa: F401 - Register post signal handlers
        import engine.utils  # noqa: F401 - Register asset signal handlers

        # Teach Pillow to decode HEIC/HEIF (iPhone camera default). Optional
        # dependency — if pillow-heif isn't installed, uploads of those
        # formats will fail the extension validator downstream, which is
        # a clearer failure mode than a silent decode error.
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except ImportError:
            pass
