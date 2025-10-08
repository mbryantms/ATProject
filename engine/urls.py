from django.urls import path

from .views import (
    PostDetailView,
    home,
)

urlpatterns = [
    path("", home, name="home"),
    path("posts/<slug:slug>/", PostDetailView.as_view(), name="post-detail"),
]
