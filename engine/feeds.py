"""
RSS and Atom feeds for published posts.
"""

from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Atom1Feed

from .models import Post, SiteSettings


class PostFeed(Feed):
    """RSS 2.0 feed of the latest published posts."""

    def title(self):
        settings = SiteSettings.load()
        return settings.site_name or "Architextual"

    def link(self):
        settings = SiteSettings.load()
        return settings.site_url or "/"

    def description(self):
        settings = SiteSettings.load()
        return settings.site_description or "Latest posts"

    def items(self):
        return (
            Post.objects.published()
            .public()
            .select_related("author")
            .order_by("-published_at")[:20]
        )

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.description or item.abstract or ""

    def item_link(self, item):
        return item.get_absolute_url()

    def item_pubdate(self, item):
        return item.published_at

    def item_updateddate(self, item):
        return item.updated_at

    def item_author_name(self, item):
        return item.author.get_full_name() or item.author.username

    def item_categories(self, item):
        return list(item.tags.values_list("name", flat=True))


class PostAtomFeed(PostFeed):
    """Atom 1.0 feed of the latest published posts."""

    feed_type = Atom1Feed
    subtitle = PostFeed.description
