"""
URL configuration for ATProject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import include, path

from engine.feeds import (
    CategoryAtomFeed,
    CategoryFeed,
    FeaturedAtomFeed,
    FeaturedFeed,
    PostAtomFeed,
    PostFeed,
    SeriesAtomFeed,
    SeriesFeed,
    TagAtomFeed,
    TagFeed,
)
from engine.sitemaps import (
    CategorySitemap,
    PostSitemap,
    SeriesSitemap,
    StaticSitemap,
    TagSitemap,
)


def health_check(request):
    """
    Health check endpoint for Railway/load balancers.
    Returns 200 OK if the application is running.
    """
    return JsonResponse({"status": "ok"}, status=200)


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
        f"Disallow: /{settings.ADMIN_URL}",
        "Disallow: /api/",
        "Disallow: /search/",
        "",
        f"Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


sitemaps = {
    "posts": PostSitemap,
    "series": SeriesSitemap,
    "categories": CategorySitemap,
    "tags": TagSitemap,
    "static": StaticSitemap,
}

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("robots.txt", robots_txt, name="robots-txt"),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("feed/", PostFeed(), name="post-feed-rss"),
    path("feed/atom/", PostAtomFeed(), name="post-feed-atom"),
    path("feed/featured/", FeaturedFeed(), name="featured-feed-rss"),
    path("feed/featured/atom/", FeaturedAtomFeed(), name="featured-feed-atom"),
    path("feed/tag/<slug:slug>/", TagFeed(), name="tag-feed-rss"),
    path("feed/tag/<slug:slug>/atom/", TagAtomFeed(), name="tag-feed-atom"),
    path(
        "feed/category/<slug:slug>/",
        CategoryFeed(),
        name="category-feed-rss",
    ),
    path(
        "feed/category/<slug:slug>/atom/",
        CategoryAtomFeed(),
        name="category-feed-atom",
    ),
    path("feed/series/<slug:slug>/", SeriesFeed(), name="series-feed-rss"),
    path(
        "feed/series/<slug:slug>/atom/",
        SeriesAtomFeed(),
        name="series-feed-atom",
    ),
    path("api/", include("engine.api.urls")),
    path("", include("engine.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Django Debug Toolbar
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass


def custom_404(request, exception):
    return render(request, "404.html", status=404)


handler404 = custom_404
