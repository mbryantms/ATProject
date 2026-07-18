from django.contrib.sitemaps import Sitemap
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from engine.models import Category, Post, Series, Tag


def _visible_post_filter(prefix="posts__"):
    """Q matching only publicly-visible posts across an M2M/related join.

    Taxonomy models (Series/Category/Tag) have no soft-delete manager, so a
    plain ``posts__status="published"`` join does NOT exclude soft-deleted or
    future-dated posts — a deleted or scheduled post could keep its taxonomy
    page in the sitemap. This mirrors ``PostQuerySet.published().public()``:
    published, PUBLIC, live, not soft-deleted, not expired.
    """
    now = timezone.now()
    return Q(
        Q(**{f"{prefix}expire_at__isnull": True})
        | Q(**{f"{prefix}expire_at__gt": now}),
        **{
            f"{prefix}status": Post.Status.PUBLISHED,
            f"{prefix}visibility": Post.Visibility.PUBLIC,
            f"{prefix}is_deleted": False,
            f"{prefix}published_at__isnull": False,
            f"{prefix}published_at__lte": now,
        },
    )


class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8
    protocol = "https"

    def items(self):
        return Post.objects.published().public().order_by("-published_at")

    def lastmod(self, obj):
        return obj.updated_at or obj.published_at

    def location(self, obj):
        return obj.get_absolute_url()


class SeriesSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6
    protocol = "https"

    def items(self):
        return (
            Series.objects.filter(_visible_post_filter()).distinct().order_by("title")
        )

    def lastmod(self, obj):
        latest = (
            obj.posts.filter(
                Q(expire_at__isnull=True) | Q(expire_at__gt=timezone.now()),
                status=Post.Status.PUBLISHED,
                visibility=Post.Visibility.PUBLIC,
                is_deleted=False,
                published_at__isnull=False,
                published_at__lte=timezone.now(),
            )
            .order_by("-updated_at")
            .first()
        )
        return latest.updated_at if latest else obj.updated_at

    def location(self, obj):
        return obj.get_absolute_url()


class CategorySitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5
    protocol = "https"

    def items(self):
        return (
            Category.objects.filter(_visible_post_filter()).distinct().order_by("name")
        )

    def location(self, obj):
        return obj.get_absolute_url()


class TagSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.4
    protocol = "https"

    def items(self):
        return (
            Tag.objects.filter(_visible_post_filter(), is_active=True)
            .distinct()
            .order_by("name")
        )

    def location(self, obj):
        return obj.get_absolute_url()


class StaticSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5
    protocol = "https"

    def items(self):
        return [
            "index",
            "post-archive",
            "about",
            "tag-list",
            "category-list",
            "series-list",
            "feed-index",
        ]

    def location(self, item):
        return reverse(item)
