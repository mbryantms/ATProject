from engine.models import SiteSettings


class SEOContextMixin:
    """Mixin that provides default SEO context variables from SiteSettings."""

    seo_title = ""
    seo_description = ""
    seo_og_type = "website"

    def get_seo_context(self):
        settings = SiteSettings.load()
        site_url = settings.site_url.rstrip("/") if settings.site_url else ""
        return {
            "seo_title": self.seo_title or settings.site_name or "Architextual",
            "seo_description": self.seo_description or settings.site_description,
            "seo_canonical": f"{site_url}{self.request.path}",
            "seo_image": settings.default_og_image_url,
            "seo_og_type": self.seo_og_type,
            "seo_noindex": False,
            "seo_twitter_card": "summary",
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_seo_context())
        return context
