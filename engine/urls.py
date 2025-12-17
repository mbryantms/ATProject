from django.urls import path

from .views import (
    IndexView,
    PostArchiveView,
    PostDetailView,
    TagArchiveView,
    TagListView,
)

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("posts/", PostArchiveView.as_view(), name="post-archive"),
    path("posts/<slug:slug>/", PostDetailView.as_view(), name="post-detail"),
    path("tags/", TagListView.as_view(), name="tag-list"),
    path("tags/<slug:slug>/", TagArchiveView.as_view(), name="tag-archive"),
]
