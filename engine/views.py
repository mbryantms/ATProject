from django.db.models import F
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import DetailView

from .models import Post


def home(request):
    """Render the base template so it can be viewed directly."""
    return render(request, "base.html")


def lorem(request):
    return render(request, "delete/lorem.html", {"page_title": "Typography"})


def admonitions(request):
    return render(request, "delete/admonitions.html", {"page_title": "Admonitions"})


def lists(request):
    return render(request, "delete/lists.html", {"page_title": "Lists"})


def block_elements(request):
    return render(
        request, "delete/block-elements.html", {"page_title": "Block Elements"}
    )


def links(request):
    return render(request, "delete/links.html", {"page_title": "Links"})


class PostDetailView(DetailView):
    """
    Shows a single post. Anonymous users can see only published+visible posts.
    Staff can see any status via direct slug.
    """

    model = Post
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "posts/post_detail.html"
    context_object_name = "post"

    def get_queryset(self):
        qs = Post.all_objects.select_related("author", "series").prefetch_related(
            "categories", "tags", "co_authors", "related_posts"
        )
        user = self.request.user
        now = timezone.now()
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            # Staff can view anything (including soft-deleted for diagnostics)
            return qs
        # Public visitors: published, visible, not soft-deleted
        return qs.filter(
            is_deleted=False,
            status=Post.Status.PUBLISHED,
            visibility__in=[Post.Visibility.PUBLIC, Post.Visibility.UNLISTED],
            published_at__isnull=False,
            published_at__lte=now,
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        # Increment view counter for public impressions only
        user = self.request.user
        is_staff = user.is_authenticated and (user.is_staff or user.is_superuser)
        if not is_staff and obj.is_published:
            Post.objects.filter(pk=obj.pk).update(view_count=F("view_count") + 1)
            obj.view_count += 1  # keep in-memory object in sync
        return obj

    def get_context_data(self, **kwargs):
        """Add backlinks and other context data to the template."""
        context = super().get_context_data(**kwargs)
        post = self.object

        # Get backlinks (posts that link to this post)
        from engine.links.extractor import get_backlinks_for_post

        backlinks = get_backlinks_for_post(
            post,
            published_only=True,
            public_only=True
        )

        context['backlinks'] = backlinks
        context['backlinks_count'] = backlinks.count()

        similar_posts = list(post.get_similar_posts(limit=6))
        context['similar_posts'] = similar_posts
        context['similar_posts_count'] = len(similar_posts)

        return context
