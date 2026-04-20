"""
RSS 2.0 and Atom 1.0 feeds.

A single ``BasePostFeed`` holds the shared item rendering logic; concrete
subclasses pick the queryset (global, by tag, by category, by series, or
featured-only) and the channel-level metadata. Each RSS feed has an Atom twin
that swaps ``feed_type`` to ``Atom1Feed`` — Django's syndication framework
handles the rest.
"""

import mimetypes

from django.conf import settings as django_settings
from django.contrib.syndication.views import Feed
from django.http import Http404
from django.utils.feedgenerator import Atom1Feed, Stylesheet
from django.utils.xmlutils import SimplerXMLGenerator

from .models import Category, Post, Series, SiteSettings, Tag, TagAlias

DEFAULT_ITEM_LIMIT = 20

# XSLT stylesheets that give the raw RSS/Atom XML a human-readable rendering
# in browsers. Feed readers ignore the <?xml-stylesheet?> processing
# instruction and consume the XML as normal. See static/feeds/*.xsl.
RSS_STYLESHEET = Stylesheet("/static/feeds/rss.xsl", media="screen")
ATOM_STYLESHEET = Stylesheet("/static/feeds/atom.xsl", media="screen")


class StyledAtomFeed(Atom1Feed):
    """Atom feed that emits a ``<?xml-stylesheet?>`` PI like RssFeed does.

    Django's ``Atom1Feed.write()`` skips the ``add_stylesheets(handler)`` call
    that ``RssFeed.write()`` makes between ``startDocument()`` and the root
    element, so stylesheet PIs never appear on Atom output. We override both
    hooks minimally — everything else remains Django's implementation.
    """

    def add_stylesheets(self, handler):
        for stylesheet in self.feed["stylesheets"] or []:
            handler.processingInstruction("xml-stylesheet", stylesheet)

    def write(self, outfile, encoding):
        handler = SimplerXMLGenerator(outfile, encoding, short_empty_elements=True)
        handler.startDocument()
        self.add_stylesheets(handler)
        handler.startElement("feed", self.root_attributes())
        self.add_root_elements(handler)
        self.write_items(handler)
        handler.endElement("feed")


class BasePostFeed(Feed):
    """Shared rendering for every site feed."""

    # Inherit Feed.feed_type (Rss201rev2Feed) by default; Atom subclasses
    # override to StyledAtomFeed. Do not assign None here — that would shadow
    # the parent default and crash get_feed() with `'NoneType' object is not callable`.

    # Every RSS feed ships with a browser-facing XSLT rendering. Atom variants
    # override this to point at atom.xsl.
    stylesheets = [RSS_STYLESHEET]

    # ---------- channel-level (override per subclass when scoped) ----------

    def title(self):
        return SiteSettings.load().site_name or "Architextual"

    def link(self):
        return SiteSettings.load().site_url or "/"

    def description(self):
        return SiteSettings.load().site_description or "Latest posts"

    def language(self):
        return django_settings.LANGUAGE_CODE

    # ---------- items ----------

    def base_queryset(self):
        return (
            Post.objects.published()
            .public()
            .select_related("author")
            .prefetch_related("tags", "categories", "co_authors")
            .order_by("-published_at")
        )

    def items(self):
        return self.base_queryset()[:DEFAULT_ITEM_LIMIT]

    # ---------- per-item ----------

    def _site_url(self):
        return SiteSettings.load().site_url or ""

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        # Full HTML body, with browser-only chrome stripped (heading/math
        # copy buttons, duplicate reference-anchor numbers). RSS readers
        # render this as the post body; Atom readers render it as
        # <summary type="html">.
        return item.get_feed_html()

    def item_link(self, item):
        return f"{self._site_url()}{item.get_absolute_url()}"

    item_guid_is_permalink = False

    def item_guid(self, item):
        # Stable identifier independent of slug renames.
        return f"post:{item.pk}"

    def item_pubdate(self, item):
        return item.published_at

    def item_updateddate(self, item):
        return item.updated_at

    def item_author_name(self, item):
        return item.author.get_full_name() or item.author.username

    def item_categories(self, item):
        # Expose both taxonomies; readers treat <category> as a flat list.
        return [
            *item.tags.values_list("name", flat=True),
            *item.categories.values_list("name", flat=True),
        ]

    def item_enclosure_url(self, item):
        return item.get_og_image_url() or None

    def item_enclosure_mime_type(self, item):
        url = self.item_enclosure_url(item)
        if not url:
            return None
        guessed, _ = mimetypes.guess_type(url)
        return guessed or "image/jpeg"

    def item_enclosure_length(self, item):
        # RSS spec requires the attribute; readers ignore the value in practice
        # and computing the real byte length per item is not worth the cost.
        return "0" if self.item_enclosure_url(item) else None


# ----------------------------------------------------------------------------
# Global feed
# ----------------------------------------------------------------------------


class PostFeed(BasePostFeed):
    """RSS 2.0 feed of the latest published posts."""


class PostAtomFeed(PostFeed):
    """Atom 1.0 twin of :class:`PostFeed`."""

    feed_type = StyledAtomFeed
    stylesheets = [ATOM_STYLESHEET]
    subtitle = PostFeed.description


# ----------------------------------------------------------------------------
# Tag feed (alias-aware)
# ----------------------------------------------------------------------------


class TagFeed(BasePostFeed):
    """Posts tagged with a single tag. Resolves tag aliases server-side."""

    def get_object(self, request, slug):
        try:
            return Tag.objects.get(slug=slug, is_active=True)
        except Tag.DoesNotExist:
            try:
                alias = TagAlias.objects.select_related("tag").get(
                    slug=slug, tag__is_active=True
                )
                return alias.tag
            except TagAlias.DoesNotExist:
                raise Http404("Tag not found")

    def title(self, obj):
        site_name = SiteSettings.load().site_name or "Architextual"
        return f"{site_name} — Posts tagged “{obj.name}”"

    def link(self, obj):
        return f"{self._site_url()}{obj.get_absolute_url()}"

    def description(self, obj):
        return obj.description or f"Posts tagged “{obj.name}”."

    def items(self, obj):
        return self.base_queryset().filter(tags=obj)[:DEFAULT_ITEM_LIMIT]


class TagAtomFeed(TagFeed):
    feed_type = StyledAtomFeed
    stylesheets = [ATOM_STYLESHEET]
    subtitle = TagFeed.description


# ----------------------------------------------------------------------------
# Category feed
# ----------------------------------------------------------------------------


class CategoryFeed(BasePostFeed):
    """Posts in a single category."""

    def get_object(self, request, slug):
        try:
            return Category.objects.get(slug=slug)
        except Category.DoesNotExist:
            raise Http404("Category not found")

    def title(self, obj):
        site_name = SiteSettings.load().site_name or "Architextual"
        return f"{site_name} — Category: {obj.name}"

    def link(self, obj):
        return f"{self._site_url()}{obj.get_absolute_url()}"

    def description(self, obj):
        return obj.description or f"Posts in category “{obj.name}”."

    def items(self, obj):
        return self.base_queryset().filter(categories=obj)[:DEFAULT_ITEM_LIMIT]


class CategoryAtomFeed(CategoryFeed):
    feed_type = StyledAtomFeed
    stylesheets = [ATOM_STYLESHEET]
    subtitle = CategoryFeed.description


# ----------------------------------------------------------------------------
# Series feed
# ----------------------------------------------------------------------------


class SeriesFeed(BasePostFeed):
    """Posts in a series, ordered for reading (series_order, then date)."""

    def get_object(self, request, slug):
        try:
            return Series.objects.get(slug=slug)
        except Series.DoesNotExist:
            raise Http404("Series not found")

    def title(self, obj):
        site_name = SiteSettings.load().site_name or "Architextual"
        return f"{site_name} — Series: {obj.title}"

    def link(self, obj):
        return f"{self._site_url()}{obj.get_absolute_url()}"

    def description(self, obj):
        return obj.description or f"Posts in series “{obj.title}”."

    def items(self, obj):
        from django.db.models import F

        return (
            self.base_queryset()
            .filter(series=obj)
            .order_by(F("series_order").asc(nulls_last=True), "published_at")[
                :DEFAULT_ITEM_LIMIT
            ]
        )


class SeriesAtomFeed(SeriesFeed):
    feed_type = StyledAtomFeed
    stylesheets = [ATOM_STYLESHEET]
    subtitle = SeriesFeed.description


# ----------------------------------------------------------------------------
# Featured feed
# ----------------------------------------------------------------------------


class FeaturedFeed(BasePostFeed):
    """Featured posts only."""

    def title(self):
        site_name = SiteSettings.load().site_name or "Architextual"
        return f"{site_name} — Featured"

    def description(self):
        return SiteSettings.load().site_description or "Featured posts."

    def items(self):
        return self.base_queryset().filter(is_featured=True)[:DEFAULT_ITEM_LIMIT]


class FeaturedAtomFeed(FeaturedFeed):
    feed_type = StyledAtomFeed
    stylesheets = [ATOM_STYLESHEET]
    subtitle = FeaturedFeed.description
