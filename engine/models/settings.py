from django.core.cache import cache
from django.db import models


class SiteSettings(models.Model):
    """Singleton model for site-wide settings. Only one row (pk=1) exists."""

    show_edit_buttons = models.BooleanField(
        default=True,
        help_text="Show admin edit links on post detail pages for staff users.",
    )
    enable_scheduled_publishing = models.BooleanField(
        default=False,
        help_text="When enabled, a Celery Beat task runs every minute to publish posts whose published_at time has passed.",
    )

    # --- SEO & Social ---
    site_name = models.CharField(
        max_length=100,
        default="Architextual",
        help_text="Site name used in OpenGraph tags and structured data.",
    )
    site_description = models.CharField(
        max_length=300,
        blank=True,
        help_text="Default meta description for pages without their own.",
    )
    site_url = models.URLField(
        blank=True,
        help_text="Canonical base URL, no trailing slash (e.g. https://architextual.net).",
    )
    default_og_image_url = models.URLField(
        blank=True,
        help_text="Default Open Graph image URL when no page-specific image exists.",
    )
    twitter_handle = models.CharField(
        max_length=50,
        blank=True,
        help_text="Twitter/X handle for twitter:site tag (e.g. @username).",
    )

    # --- Zotero Integration ---
    zotero_library_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Numeric Zotero user or group library ID (find at zotero.org/settings/keys, NOT your username).",
    )
    zotero_library_type = models.CharField(
        max_length=10,
        blank=True,
        choices=[("user", "User"), ("group", "Group")],
        default="user",
        help_text="Whether this is a personal or group library.",
    )
    zotero_api_key = models.CharField(
        max_length=100,
        blank=True,
        help_text="Zotero API key (generate at zotero.org/settings/keys).",
    )
    zotero_last_sync_version = models.IntegerField(
        default=0,
        help_text="Zotero library version at last sync (for incremental sync).",
    )
    zotero_last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last successful Zotero sync.",
    )

    # --- Bibliography ---
    default_citation_style = models.CharField(
        max_length=100,
        default="apa",
        blank=True,
        help_text="Default CSL citation style (e.g., apa, chicago-author-date, mla).",
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
