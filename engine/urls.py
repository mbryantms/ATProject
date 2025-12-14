from django.urls import path

from .views import (
    PostArchiveView,
    PostDetailView,
    home,
)

urlpatterns = [
    path("", PostArchiveView.as_view(), name="post-archive"),
    path("posts/<slug:slug>/", PostDetailView.as_view(), name="post-detail"),
]
