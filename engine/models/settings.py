from django.core.cache import cache
from django.db import models


class SiteSettings(models.Model):
    """Singleton model for site-wide settings. Only one row (pk=1) exists."""

    show_edit_buttons = models.BooleanField(
        default=True,
        help_text="Show admin edit links on post detail pages for staff users.",
    )

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete("site_settings")

    # Cache site settings for 24 hours to minimize DB wake-ups.
    # Saving via admin invalidates the cache immediately.
    CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours

    @classmethod
    def load(cls):
        settings = cache.get("site_settings")
        if settings is None:
            settings, _ = cls.objects.get_or_create(pk=1)
            cache.set("site_settings", settings, timeout=cls.CACHE_TIMEOUT)
        return settings
