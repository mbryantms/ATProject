from collections import OrderedDict

from django.core.cache import cache
from django.db.models import Count, F, Max, Min, Q, Sum
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from .mixins import SEOContextMixin
from .models import Category, Page, Post, Series, SiteSettings, Tag, TagAlias


class IndexView(SEOContextMixin, TemplateView):
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

        # Get the page object for intro content and featured config
        try:
            page = Page.objects.prefetch_related(
                "pagefeaturedtag_set__tag",
                "pagefeaturedcategory_set__category",
            ).get(slug=self.PAGE_SLUG, is_active=True)
            context["intro_html"] = page.content_html
            featured_tags_config = page.get_featured_tags_config()
            featured_categories_config = page.get_featured_categories_config()
        except Page.DoesNotExist:
            context["intro_html"] = ""
            featured_tags_config = []
            featured_categories_config = []

        # Get latest posts for "Newest" section
        base_qs = self.get_base_queryset()
        context["newest_posts"] = base_qs[:5]

        # Batch-load posts for all featured tags in a single query,
        # then group by tag in Python to avoid N+1 queries.
        active_tags = [c["tag"] for c in featured_tags_config if c["tag"].is_active]
        tag_sections = []
        if active_tags:
            tag_posts = base_qs.filter(tags__in=active_tags)
            # Build a dict: tag_id -> list of posts (up to 5 each)
            posts_by_tag = {}
            for post in tag_posts:
                for tag in post.tags.all():
                    if tag.id not in posts_by_tag:
                        posts_by_tag[tag.id] = []
                    if len(posts_by_tag[tag.id]) < 5:
                        posts_by_tag[tag.id].append(post)

            for config in featured_tags_config:
                tag = config["tag"]
                if tag.is_active and posts_by_tag.get(tag.id):
                    tag_sections.append(
                        {
                            "title": config["display_title"],
                            "tag": tag,
                            "posts": posts_by_tag[tag.id],
                        }
                    )

        context["tag_sections"] = tag_sections

        # Batch-load posts for all featured categories in a single query.
        featured_categories = [c["category"] for c in featured_categories_config]
        category_sections = []
        if featured_categories:
            cat_posts = base_qs.filter(
                categories__in=featured_categories
            ).prefetch_related("categories")
            posts_by_cat = {}
            for post in cat_posts:
                for cat in post.categories.all():
                    if cat.id not in posts_by_cat:
                        posts_by_cat[cat.id] = []
                    if len(posts_by_cat[cat.id]) < 5:
                        posts_by_cat[cat.id].append(post)

            for config in featured_categories_config:
                category = config["category"]
                if posts_by_cat.get(category.id):
                    category_sections.append(
                        {
                            "title": config["display_title"],
                            "category": category,
                            "posts": posts_by_cat[category.id],
                        }
                    )

        context["category_sections"] = category_sections

        return context


class PostArchiveView(SEOContextMixin, TemplateView):
    """
    Landing page showing all published posts in reverse chronological order,
    grouped by year.
    """

    template_name = "posts/post_archive.html"
    seo_title = "All Posts"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        current_sort = self.request.GET.get("sort", "date")
        if current_sort not in ("date", "title"):
            current_sort = "date"

        # Get published, public posts — defer heavy text fields not needed for listing
        deferred = (
            "content_markdown",
            "content_html_cached",
            "table_of_contents",
            "search_vector",
        )
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            posts = (
                Post.all_objects.filter(is_deleted=False)
                .defer(*deferred)
                .select_related("author")
                .prefetch_related("tags")
            )
        else:
            posts = (
                Post.objects.published()
                .public()
                .defer(*deferred)
                .select_related("author")
                .prefetch_related("tags")
            )

        if current_sort == "title":
            posts = posts.order_by("title")
        else:
            posts = posts.order_by("-published_at")

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
        context["current_sort"] = current_sort
        return context


class TagArchiveView(SEOContextMixin, TemplateView):
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
        tag = (
            Tag.objects.select_related("parent")
            .prefetch_related("aliases")
            .get(slug=slug, is_active=True)
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

        # SEO overrides
        context["seo_title"] = f"Posts tagged: {tag.name}"
        if tag.description:
            context["seo_description"] = tag.description[:300]

        return context


class TagListView(SEOContextMixin, TemplateView):
    """
    Display all active tags with post counts.

    Supports display options via query parameters:
    - show=description,color,icon,namespace,hierarchy (comma-separated)
    - sort=name|count|rank (default: name)
    - group=namespace (group tags by namespace)
    """

    template_name = "posts/tag_list.html"
    seo_title = "Tags"

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
                posts__visibility__in=[
                    Post.Visibility.PUBLIC,
                    Post.Visibility.UNLISTED,
                ],
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


class CategoryArchiveView(SEOContextMixin, TemplateView):
    """
    Display all posts in a specific category, grouped by year.
    Includes hierarchical navigation (ancestors, children, siblings).
    """

    template_name = "posts/category_archive.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get("slug")
        user = self.request.user

        try:
            category = Category.objects.select_related("parent").get(slug=slug)
        except Category.DoesNotExist:
            raise Http404("Category not found")

        # Get posts in this category
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            posts = (
                Post.all_objects.filter(is_deleted=False, categories=category)
                .select_related("author")
                .order_by("-published_at")
            )
        else:
            posts = (
                Post.objects.published()
                .public()
                .filter(categories=category)
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

        # Hierarchical navigation
        ancestors = category.get_ancestors()
        children = category.children.order_by("name")

        if category.parent:
            siblings = category.parent.children.exclude(pk=category.pk).order_by("name")
        else:
            siblings = (
                Category.objects.filter(parent__isnull=True)
                .exclude(pk=category.pk)
                .order_by("name")
            )

        context["category"] = category
        context["posts_by_year"] = posts_by_year
        context["total_posts"] = sum(len(posts) for posts in posts_by_year.values())
        context["ancestors"] = ancestors
        context["children"] = children
        context["siblings"] = siblings

        # SEO overrides
        context["seo_title"] = f"Category: {category.name}"
        if category.description:
            context["seo_description"] = category.description[:300]

        return context


class CategoryListView(SEOContextMixin, TemplateView):
    """
    Display all categories with post counts.

    Supports query parameters:
    - sort=name|count (default: name)
    - show=description,hierarchy (comma-separated)
    """

    template_name = "posts/category_list.html"
    seo_title = "Categories"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        show_param = self.request.GET.get("show", "")
        show_options = [opt.strip() for opt in show_param.split(",") if opt.strip()]
        sort_by = self.request.GET.get("sort", "name")

        # Build post count filter based on user permissions
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            post_filter = Q(posts__is_deleted=False)
        else:
            post_filter = Q(
                posts__is_deleted=False,
                posts__status=Post.Status.PUBLISHED,
                posts__visibility__in=[
                    Post.Visibility.PUBLIC,
                    Post.Visibility.UNLISTED,
                ],
                posts__published_at__isnull=False,
                posts__published_at__lte=now,
            )

        categories = Category.objects.annotate(
            post_count=Count("posts", filter=post_filter)
        ).select_related("parent")

        if sort_by == "count":
            categories = categories.order_by("-post_count", "name")
        else:
            categories = categories.order_by("name")

        context["categories"] = categories
        context["show_description"] = "description" in show_options
        context["show_hierarchy"] = "hierarchy" in show_options
        context["show_any_extra"] = bool(show_options)
        context["current_show"] = show_options
        context["current_sort"] = sort_by
        context["base_url"] = f"?sort={sort_by}"
        context["total_categories"] = categories.count()
        context["total_posts"] = sum(c.post_count for c in categories)
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


class PageView(SEOContextMixin, TemplateView):
    """
    Render a static page from the Page model.

    Used for editable pages like About, etc.
    """

    template_name = "page.html"
    page_slug = None  # Set in URL config or subclass

    def get_page_slug(self):
        """Get the page slug from URL kwargs or class attribute."""
        return self.kwargs.get("slug") or self.page_slug

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.get_page_slug()

        try:
            page = Page.objects.get(slug=slug, is_active=True)
            context["page"] = page
            context["page_title"] = page.title
            context["content_html"] = page.content_html
            context["seo_title"] = page.title
        except Page.DoesNotExist:
            raise Http404(f"Page '{slug}' not found")

        return context


class PostDetailView(SEOContextMixin, DetailView):
    """
    Shows a single post. Anonymous users can see only published+visible posts.
    Staff can see any status via direct slug.
    """

    model = Post
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "posts/post_detail.html"
    context_object_name = "post"
    seo_og_type = "article"

    def get_queryset(self):
        qs = Post.all_objects.select_related("author", "series").prefetch_related(
            "categories",
            "tags",
            "co_authors",
            "related_posts",
            "post_assets__asset",  # Prefetch for asset resolution in markdown
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

        backlinks = get_backlinks_for_post(post, published_only=True, public_only=True)

        context["backlinks"] = backlinks
        context["backlinks_count"] = backlinks.count()

        # Cache similar posts for 1 hour (expensive computation)
        cache_key = f"similar_posts:{post.pk}"
        similar_posts = cache.get(cache_key)
        if similar_posts is None:
            similar_posts = list(post.get_similar_posts(limit=6))
            cache.set(cache_key, similar_posts, 3600)  # 1 hour
        context["similar_posts"] = similar_posts
        context["similar_posts_count"] = len(similar_posts)

        # Get citation count for bibliography metadata and TOC
        citations_count = post.citations.count()
        context["citations_count"] = citations_count

        if post.show_toc:
            context["toc_nodes"] = post.get_render_toc(
                backlinks_count=context["backlinks_count"],
                similar_posts_count=context["similar_posts_count"],
                citations_count=citations_count,
            )
        else:
            context["toc_nodes"] = []

        # Series prev/next navigation
        if post.series:
            user = self.request.user
            is_staff = user.is_authenticated and (user.is_staff or user.is_superuser)
            if is_staff:
                siblings = (
                    Post.all_objects.filter(series=post.series, is_deleted=False)
                    .order_by(F("series_order").asc(nulls_last=True), "published_at")
                    .only("pk", "title", "slug", "series_order", "published_at")
                )
            else:
                siblings = (
                    Post.objects.published()
                    .public()
                    .filter(series=post.series)
                    .order_by(F("series_order").asc(nulls_last=True), "published_at")
                    .only("pk", "title", "slug", "series_order", "published_at")
                )
            sibling_list = list(siblings)
            current_idx = None
            for i, s in enumerate(sibling_list):
                if s.pk == post.pk:
                    current_idx = i
                    break
            if current_idx is not None:
                context["series_prev"] = (
                    sibling_list[current_idx - 1] if current_idx > 0 else None
                )
                context["series_next"] = (
                    sibling_list[current_idx + 1]
                    if current_idx < len(sibling_list) - 1
                    else None
                )

        # --- SEO context ---
        settings = SiteSettings.load()
        site_url = self._get_site_url(settings)
        og_image = post.get_og_image_url() or settings.default_og_image_url

        context["seo_title"] = post.title
        context["seo_description"] = post.get_meta_description()
        context["seo_canonical"] = post.get_canonical_url(site_url)
        context["seo_image"] = og_image
        context["seo_og_type"] = "article"
        context["seo_twitter_card"] = "summary_large_image" if og_image else "summary"
        context["seo_noindex"] = post.should_noindex()
        context["seo_published_time"] = post.published_at
        context["seo_modified_time"] = post.updated_at
        context["seo_author"] = post.author.get_full_name() or post.author.username
        context["seo_tags"] = list(post.tags.values_list("name", flat=True))
        category_names = list(post.categories.values_list("name", flat=True))
        context["seo_section"] = category_names[0] if category_names else None
        context["seo_keywords"] = context["seo_tags"] + category_names
        context["seo_word_count"] = post.word_count
        context["seo_language"] = post.language

        # Breadcrumbs
        breadcrumbs = [{"name": "Home", "url": f"{site_url}/"}]
        first_cat = post.categories.first()
        if first_cat:
            breadcrumbs.append(
                {
                    "name": first_cat.name,
                    "url": f"{site_url}{first_cat.get_absolute_url()}",
                }
            )
        breadcrumbs.append(
            {"name": post.title, "url": f"{site_url}{post.get_absolute_url()}"}
        )
        context["seo_breadcrumbs"] = breadcrumbs

        return context


class SeriesListView(SEOContextMixin, ListView):
    """List all series that have at least one published, public post."""

    model = Series
    template_name = "posts/series_list.html"
    context_object_name = "series_list"
    seo_title = "Series"

    def get_queryset(self):
        user = self.request.user
        now = timezone.now()

        if user.is_authenticated and (user.is_staff or user.is_superuser):
            post_filter = Q(posts__is_deleted=False)
        else:
            post_filter = Q(
                posts__is_deleted=False,
                posts__status=Post.Status.PUBLISHED,
                posts__visibility=Post.Visibility.PUBLIC,
                posts__published_at__isnull=False,
                posts__published_at__lte=now,
            )

        current_sort = self.request.GET.get("sort", "name")
        if current_sort not in ("name", "count"):
            current_sort = "name"

        qs = Series.objects.annotate(
            post_count=Count("posts", filter=post_filter)
        ).filter(post_count__gt=0)

        if current_sort == "count":
            qs = qs.order_by("-post_count", "title")
        else:
            qs = qs.order_by("title")

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_sort = self.request.GET.get("sort", "name")
        if current_sort not in ("name", "count"):
            current_sort = "name"
        context["current_sort"] = current_sort
        context["total_series"] = (
            context["series_list"].count()
            if hasattr(context["series_list"], "count")
            else len(context["series_list"])
        )
        return context


class SeriesDetailView(SEOContextMixin, DetailView):
    """Display a single series with its posts in order."""

    model = Series
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "posts/series_detail.html"
    context_object_name = "series"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        series = self.object
        user = self.request.user

        if user.is_authenticated and (user.is_staff or user.is_superuser):
            posts = (
                Post.all_objects.filter(series=series, is_deleted=False)
                .select_related("author")
                .order_by(F("series_order").asc(nulls_last=True), "published_at")
            )
        else:
            posts = (
                Post.objects.published()
                .public()
                .filter(series=series)
                .select_related("author")
                .order_by(F("series_order").asc(nulls_last=True), "published_at")
            )

        context["posts"] = posts
        context["total_posts"] = posts.count()

        stats = posts.aggregate(
            first_published=Min("published_at"),
            last_published=Max("published_at"),
            total_words=Sum("word_count"),
            total_reading_time=Sum("reading_time_minutes"),
        )
        context.update(stats)

        # SEO overrides
        context["seo_title"] = series.title
        if series.description:
            context["seo_description"] = series.description[:300]

        return context
