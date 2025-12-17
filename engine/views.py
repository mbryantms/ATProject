from collections import OrderedDict

from django.db.models import Count, F, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from .models import Page, Post, Tag, TagAlias


class IndexView(TemplateView):
    """
    Homepage showing an intro section and multi-column content sections.

    Displays:
    - Editable intro paragraph (from Page model with slug 'home-intro')
    - "Newest" section with latest posts
    - Tag-based sections configured via Page.featured_tags
    """

    template_name = "index.html"
    PAGE_SLUG = "home-intro"

    def get_base_queryset(self):
        """Get base post queryset based on user permissions."""
        user = self.request.user
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            return (
                Post.all_objects.filter(is_deleted=False)
                .select_related("author")
                .prefetch_related("tags")
                .order_by("-published_at")
            )
        return (
            Post.objects.published()
            .public()
            .select_related("author")
            .prefetch_related("tags")
            .order_by("-published_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get the page object for intro content and featured tags config
        try:
            page = Page.objects.prefetch_related(
                "pagefeaturedtag_set__tag"
            ).get(slug=self.PAGE_SLUG, is_active=True)
            context["intro_html"] = page.content_html
            featured_tags_config = page.get_featured_tags_config()
        except Page.DoesNotExist:
            context["intro_html"] = ""
            featured_tags_config = []

        # Get latest posts for "Newest" section
        base_qs = self.get_base_queryset()
        context["newest_posts"] = base_qs[:5]

        # Get posts for each featured tag (configured in admin)
        tag_sections = []
        for config in featured_tags_config:
            tag = config["tag"]
            if tag.is_active:
                posts = base_qs.filter(tags=tag)[:5]
                if posts.exists():
                    tag_sections.append({
                        "title": config["display_title"],
                        "tag": tag,
                        "posts": posts,
                    })

        context["tag_sections"] = tag_sections

        return context


class PostArchiveView(TemplateView):
    """
    Landing page showing all published posts in reverse chronological order,
    grouped by year.
    """

    template_name = "posts/post_archive.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get published, public posts ordered by publication date (newest first)
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            # Staff can see all posts
            posts = (
                Post.all_objects.filter(is_deleted=False)
                .select_related("author")
                .prefetch_related("tags")
                .order_by("-published_at")
            )
        else:
            # Public visitors see only published, public posts
            posts = (
                Post.objects.published()
                .public()
                .select_related("author")
                .prefetch_related("tags")
                .order_by("-published_at")
            )

        # Group posts by year
        posts_by_year = OrderedDict()
        for post in posts:
            if post.published_at:
                year = post.published_at.year
                if year not in posts_by_year:
                    posts_by_year[year] = []
                posts_by_year[year].append(post)

        context["posts_by_year"] = posts_by_year
        context["total_posts"] = sum(len(posts) for posts in posts_by_year.values())
        return context


class TagArchiveView(TemplateView):
    """
    Display all posts with a specific tag, grouped by year.
    Includes hierarchical navigation (ancestors and children).

    Supports tag aliases: if the slug matches an alias, redirects (301)
    to the canonical tag URL.
    """

    template_name = "posts/tag_archive.html"

    def get(self, request, *args, **kwargs):
        """Handle alias redirects before rendering."""
        slug = self.kwargs.get("slug")

        # Check if the slug is an alias
        try:
            Tag.objects.get(slug=slug, is_active=True)
        except Tag.DoesNotExist:
            # Not a canonical tag - check if it's an alias
            try:
                alias = TagAlias.objects.select_related("tag").get(
                    slug=slug, tag__is_active=True
                )
                # Redirect to canonical tag URL (301 permanent)
                return redirect("tag-archive", slug=alias.tag.slug, permanent=True)
            except TagAlias.DoesNotExist:
                raise Http404("Tag not found")

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get("slug")
        user = self.request.user

        # Get the tag (we know it exists from get())
        tag = Tag.objects.select_related("parent").prefetch_related("aliases").get(
            slug=slug, is_active=True
        )

        # Get posts with this tag
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            posts = (
                Post.all_objects.filter(is_deleted=False, tags=tag)
                .select_related("author")
                .order_by("-published_at")
            )
        else:
            posts = (
                Post.objects.published()
                .public()
                .filter(tags=tag)
                .select_related("author")
                .order_by("-published_at")
            )

        # Group posts by year
        posts_by_year = OrderedDict()
        for post in posts:
            if post.published_at:
                year = post.published_at.year
                if year not in posts_by_year:
                    posts_by_year[year] = []
                posts_by_year[year].append(post)

        # Get hierarchical navigation
        ancestors = tag.get_ancestors()
        children = tag.children.filter(is_active=True).order_by("-rank", "name")

        # Get sibling tags (other children of the same parent)
        if tag.parent:
            siblings = (
                tag.parent.children.filter(is_active=True)
                .exclude(pk=tag.pk)
                .order_by("-rank", "name")
            )
        else:
            # Root-level siblings
            siblings = (
                Tag.objects.filter(parent__isnull=True, is_active=True)
                .exclude(pk=tag.pk)
                .order_by("-rank", "name")
            )

        context["tag"] = tag
        context["posts_by_year"] = posts_by_year
        context["total_posts"] = sum(len(posts) for posts in posts_by_year.values())
        context["ancestors"] = ancestors
        context["children"] = children
        context["siblings"] = siblings
        context["aliases"] = tag.aliases.all()
        return context


class TagListView(TemplateView):
    """
    Display all active tags with post counts.

    Supports display options via query parameters:
    - show=description,color,icon,namespace,hierarchy (comma-separated)
    - sort=name|count|rank (default: name)
    - group=namespace (group tags by namespace)
    """

    template_name = "posts/tag_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        # Parse display options from query string
        show_param = self.request.GET.get("show", "")
        show_options = [opt.strip() for opt in show_param.split(",") if opt.strip()]

        sort_by = self.request.GET.get("sort", "name")
        group_by = self.request.GET.get("group", "")

        # Build post count filter based on user permissions
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            # Staff sees all non-deleted posts
            post_filter = Q(posts__is_deleted=False)
        else:
            # Public sees only published, public posts
            post_filter = Q(
                posts__is_deleted=False,
                posts__status=Post.Status.PUBLISHED,
                posts__visibility__in=[Post.Visibility.PUBLIC, Post.Visibility.UNLISTED],
                posts__published_at__isnull=False,
                posts__published_at__lte=now,
            )

        # Get tags with post counts
        tags = (
            Tag.objects.filter(is_active=True)
            .annotate(post_count=Count("posts", filter=post_filter))
            .select_related("parent")
        )

        # Sorting
        if sort_by == "count":
            tags = tags.order_by("-post_count", "name")
        elif sort_by == "rank":
            tags = tags.order_by("-rank", "name")
        else:  # default: name
            tags = tags.order_by("name")

        # Grouping by namespace
        if group_by == "namespace":
            tags_by_namespace = OrderedDict()
            # First, get all tags without namespace
            no_namespace = [t for t in tags if not t.namespace]
            if no_namespace:
                tags_by_namespace[""] = no_namespace

            # Then group by namespace
            namespaces = sorted(set(t.namespace for t in tags if t.namespace))
            for ns in namespaces:
                tags_by_namespace[ns] = [t for t in tags if t.namespace == ns]

            context["tags_by_namespace"] = tags_by_namespace
            context["grouped"] = True
        else:
            context["tags"] = tags
            context["grouped"] = False

        # Display options
        context["show_description"] = "description" in show_options
        context["show_color"] = "color" in show_options
        context["show_icon"] = "icon" in show_options
        context["show_namespace"] = "namespace" in show_options
        context["show_hierarchy"] = "hierarchy" in show_options
        context["show_any_extra"] = bool(show_options)

        # Current settings for building toggle links
        context["current_show"] = show_options
        context["current_sort"] = sort_by
        context["current_group"] = group_by

        # Build base URL for toggle links
        base_url = f"?sort={sort_by}"
        if group_by:
            base_url += f"&group={group_by}"
        context["base_url"] = base_url

        # Stats
        context["total_tags"] = tags.count()
        context["total_posts"] = sum(t.post_count for t in tags)

        return context


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

        if post.show_toc:
            context['toc_nodes'] = post.get_render_toc(
                backlinks_count=context['backlinks_count'],
                similar_posts_count=context['similar_posts_count'],
            )
        else:
            context['toc_nodes'] = []

        return context
