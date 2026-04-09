from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from engine.models import Category, Post, Series, Tag


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
            Series.objects.filter(posts__status="published", posts__visibility="public")
            .distinct()
            .order_by("title")
        )

    def lastmod(self, obj):
        latest = obj.posts.filter(status="published").order_by("-updated_at").first()
        return latest.updated_at if latest else obj.updated_at

    def location(self, obj):
        return obj.get_absolute_url()


class CategorySitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5
    protocol = "https"

    def items(self):
        return (
            Category.objects.filter(
                posts__status="published", posts__visibility="public"
            )
            .distinct()
            .order_by("name")
        )

    def location(self, obj):
        return obj.get_absolute_url()


class TagSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.4
    protocol = "https"

    def items(self):
        return (
            Tag.objects.filter(
                is_active=True, posts__status="published", posts__visibility="public"
            )
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
        return ["index", "post-archive", "about"]

    def location(self, item):
        return reverse(item)
