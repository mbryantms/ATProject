from engine.models import SiteSettings


class SEOContextMixin:
    """Mixin that provides default SEO context variables from SiteSettings."""

    seo_title = ""
    seo_description = ""
    seo_og_type = "website"

    def _get_site_url(self, settings):
        """Return absolute site URL, preferring SiteSettings, falling back to request."""
        if settings.site_url:
            return settings.site_url.rstrip("/")
        return f"{self.request.scheme}://{self.request.get_host()}"

    def get_seo_context(self):
        settings = SiteSettings.load()
        site_url = self._get_site_url(settings)
        return {
            "seo_title": self.seo_title or settings.site_name or "Architextual",
            "seo_description": self.seo_description or settings.site_description,
            "seo_canonical": f"{site_url}{self.request.path}",
            "seo_image": settings.default_og_image_url,
            "seo_og_type": self.seo_og_type,
            "seo_noindex": False,
            "seo_twitter_card": "summary",
            "seo_site_url": site_url,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_seo_context())
        return context
