"""
RSS 2.0 and Atom 1.0 feeds.

A single ``BasePostFeed`` holds the shared item rendering logic; concrete
subclasses pick the queryset (global, by tag, by category, by series, or
featured-only) and the channel-level metadata. Each RSS feed has an Atom twin
that swaps ``feed_type`` to ``Atom1Feed`` — Django's syndication framework
handles the rest.
"""

import mimetypes

from django.contrib.syndication.views import Feed
from django.http import Http404
from django.templatetags.static import static
from django.utils.feedgenerator import Atom1Feed, Rss201rev2Feed, Stylesheet
from django.utils.xmlutils import SimplerXMLGenerator

from .models import Category, Post, Series, SiteSettings, Tag, TagAlias

DEFAULT_ITEM_LIMIT = 20

# Paths to the XSLT stylesheets that give the raw RSS/Atom XML a human-readable
# rendering in browsers. Feed readers ignore the <?xml-stylesheet?> processing
# instruction and consume the XML as normal. See static/feeds/*.xsl.
#
# IMPORTANT: we resolve the URL via django.templatetags.static.static() at
# request time rather than hardcoding "/static/feeds/rss.xsl". Production uses
# CompressedManifestStaticFilesStorage (whitenoise) which serves only hashed
# filenames like feeds/rss.42666a0a.xsl, so the unhashed path would 404 and
# the browser would fall back to downloading the XML.
_RSS_XSL_PATH = "feeds/rss.xsl"
_ATOM_XSL_PATH = "feeds/atom.xsl"


#
# Why the feeds are served as ``application/xml`` and not the more specific
# ``application/rss+xml`` / ``application/atom+xml`` that Django ships by
# default:
#
# Our Django ``SecurityMiddleware`` sends ``X-Content-Type-Options: nosniff``
# on every response, forcing browsers to honor the declared Content-Type
# exactly. Safari (and some Chrome configurations) treat the two feed-specific
# MIME types as "subscribe, don't render" — the browser downloads the XML
# even when a ``<?xml-stylesheet?>`` PI is present. ``application/xml``
# routes the response through the browser's normal XML + XSLT pipeline, so
# the stylesheet is applied and the human-readable page renders.
#
# Every mainstream feed reader (Feedly, NetNewsWire, Inoreader, Miniflux,
# Tiny Tiny RSS, Fraidycat, command-line ``feedparser``) sniffs the XML body
# rather than keying off this header, so discovery and subscription are
# unaffected. Browser autodiscovery still uses ``<link rel="alternate"
# type="application/rss+xml" …>`` which we emit on every page head.
_XML_CONTENT_TYPE = "application/xml; charset=utf-8"


class StyledRssFeed(Rss201rev2Feed):
    """RSS feed served as application/xml so browsers render the XSL."""

    content_type = _XML_CONTENT_TYPE


class StyledAtomFeed(Atom1Feed):
    """Atom feed that emits a ``<?xml-stylesheet?>`` PI like RssFeed does.

    Django's ``Atom1Feed.write()`` skips the ``add_stylesheets(handler)`` call
    that ``RssFeed.write()`` makes between ``startDocument()`` and the root
    element, so stylesheet PIs never appear on Atom output. We override both
    hooks minimally — everything else remains Django's implementation.

    Also overrides ``content_type`` so browsers render the XSL (see the
    comment above ``_XML_CONTENT_TYPE`` for why).
    """

    content_type = _XML_CONTENT_TYPE

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

    # Every RSS feed goes through StyledRssFeed (application/xml + styled XSL);
    # Atom subclasses swap to StyledAtomFeed. Do not assign None here — that
    # would shadow the parent default and crash get_feed() with
    # ``'NoneType' object is not callable``.
    feed_type = StyledRssFeed

    # Every RSS feed ships with a browser-facing XSLT rendering. Atom variants
    # override ``_stylesheet_path`` to point at atom.xsl.
    _stylesheet_path = _RSS_XSL_PATH

    def stylesheets(self):
        # Resolved through static() at request time so the hashed filename
        # from CompressedManifestStaticFilesStorage is honored in production.
        return [Stylesheet(static(self._stylesheet_path), media="screen")]

    # ---------- channel-level (override per subclass when scoped) ----------

    def title(self):
        return SiteSettings.load().site_name or "Architextual"

    def link(self):
        return SiteSettings.load().site_url or "/"

    def description(self):
        return SiteSettings.load().site_description or "Latest posts"

    # ``language`` is read directly off ``self`` by Django's Feed.get_feed()
    # (see django/contrib/syndication/views.py — NOT via _get_dynamic_attr).
    # If we defined a method here, Django would pass the bound-method object
    # to the feed constructor and emit <language>&lt;bound method…&gt;</language>.
    # Leaving it unset lets Django fall back to translation.get_language().

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
    _stylesheet_path = _ATOM_XSL_PATH
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
    _stylesheet_path = _ATOM_XSL_PATH
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
    _stylesheet_path = _ATOM_XSL_PATH
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
    _stylesheet_path = _ATOM_XSL_PATH
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
    _stylesheet_path = _ATOM_XSL_PATH
    subtitle = FeaturedFeed.description
