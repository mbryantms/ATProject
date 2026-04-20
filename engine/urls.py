from django.urls import path

from .search.views import SearchPageView
from .views import (
    CategoryArchiveView,
    CategoryListView,
    FeedIndexView,
    IndexView,
    PageView,
    PostArchiveView,
    PostDetailView,
    SeriesDetailView,
    SeriesListView,
    TagArchiveView,
    TagListView,
)

urlpatterns = [
    path("search/", SearchPageView.as_view(), name="search"),
    path("", IndexView.as_view(), name="index"),
    path("posts/", PostArchiveView.as_view(), name="post-archive"),
    path("posts/<slug:slug>/", PostDetailView.as_view(), name="post-detail"),
    path("series/", SeriesListView.as_view(), name="series-list"),
    path("series/<slug:slug>/", SeriesDetailView.as_view(), name="series-detail"),
    path("tags/", TagListView.as_view(), name="tag-list"),
    path("tags/<slug:slug>/", TagArchiveView.as_view(), name="tag-archive"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path(
        "categories/<slug:slug>/",
        CategoryArchiveView.as_view(),
        name="category-archive",
    ),
    path("about/", PageView.as_view(page_slug="about"), name="about"),
    path("feeds/", FeedIndexView.as_view(), name="feed-index"),
]
