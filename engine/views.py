import math
from collections import OrderedDict

from django.core.paginator import Paginator
from django.db.models import Count, F, Max, Min, Prefetch, Q, Sum
from django.db.models.functions import ExtractYear
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from .mixins import SEOContextMixin
from .models import (
    Category,
    Page,
    Post,
    PostCitation,
    PostSimilarity,
    Series,
    SiteSettings,
    Source,
    SourceFile,
    Tag,
    TagAlias,
)

# Archive pages group posts by year. The page size is generous so a small blog
# renders every post on one page (no pager shown, unchanged UX); it only bounds
# page weight and query result size once the archive grows large.
ARCHIVE_PAGE_SIZE = 50


def _paginate_post_index(request, posts, sort="date"):
    """Paginate an ordered post queryset and group the current page into
    display sections for the shared post-index template.

    For date sort the sections are years (with true per-year totals, plus a
    year-strip entry mapping each year to the page it starts on); for title
    sort they are initial letters. Grouping applies to the current page only,
    so a section straddling a page boundary simply repeats its heading on the
    next page — standard for paged archives.

    Returns ``(page_obj, sections, year_strip, total_count)``. ``sections``
    is a list of ``{"heading", "anchor", "posts", "total"}`` dicts;
    ``year_strip`` is a list of ``{"year", "total", "page"}`` dicts (empty
    for title sort).
    """
    paginator = Paginator(posts, ARCHIVE_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    if sort == "title":
        by_letter = OrderedDict()
        for post in page_obj.object_list:
            letter = post.title[:1].upper()
            if not letter.isalpha():
                letter = "#"
            by_letter.setdefault(letter, []).append(post)
        sections = [
            {
                "heading": letter,
                "anchor": "t-num" if letter == "#" else f"t-{letter}",
                "posts": letter_posts,
                "total": None,
            }
            for letter, letter_posts in by_letter.items()
        ]
        return page_obj, sections, [], paginator.count

    # Per-year totals over the WHOLE queryset (the page only holds a slice).
    # ExtractYear and ``localtime`` below both resolve in the current timezone,
    # so section keys and totals agree.
    totals = (
        posts.filter(published_at__isnull=False)
        .prefetch_related(None)  # aggregate rows can't take prefetches
        .annotate(year=ExtractYear("published_at"))
        .values("year")
        .annotate(n=Count("pk"))
        .order_by("-year")
    )
    # Undated posts (staff viewing drafts) sort NULLS FIRST under
    # ``-published_at`` on Postgres, so they occupy the earliest offsets.
    undated_count = posts.filter(published_at__isnull=True).count()

    year_totals = {}
    year_strip = []
    offset = undated_count
    for row in totals:
        year_totals[row["year"]] = row["n"]
        year_strip.append(
            {
                "year": row["year"],
                "total": row["n"],
                "page": offset // ARCHIVE_PAGE_SIZE + 1,
            }
        )
        offset += row["n"]

    by_year = OrderedDict()
    for post in page_obj.object_list:
        if post.published_at:
            key = timezone.localtime(post.published_at).year
        else:
            key = None
        by_year.setdefault(key, []).append(post)

    sections = []
    for year, year_posts in by_year.items():
        if year is None:
            sections.append(
                {
                    "heading": "Undated",
                    "anchor": "y-undated",
                    "posts": year_posts,
                    "total": None,
                }
            )
        else:
            sections.append(
                {
                    "heading": str(year),
                    "anchor": f"y{year}",
                    "posts": year_posts,
                    "total": year_totals.get(year),
                }
            )
    return page_obj, sections, year_strip, paginator.count


def _taxonomy_post_filter(user, now):
    """Q filter for counting a taxonomy object's posts (Tag/Category/Series
    all expose the same ``posts`` related name).

    Staff count every non-deleted post; the public count must match what the
    archive pages actually list: PUBLIC and published only. Counting UNLISTED
    here would advertise the number of hidden posts and make count badges
    disagree with the archive pages.
    """
    if user.is_authenticated and (user.is_staff or user.is_superuser):
        return Q(posts__is_deleted=False)
    return Q(
        Q(posts__expire_at__isnull=True) | Q(posts__expire_at__gt=now),
        posts__is_deleted=False,
        posts__status=Post.Status.PUBLISHED,
        posts__visibility=Post.Visibility.PUBLIC,
        posts__published_at__isnull=False,
        posts__published_at__lte=now,
    )


def _attach_row_tags(sections, exclude_slug=None, limit=3):
    """Attach ``row_tags`` to each post in the paginated index sections.

    Uses the prefetched tag list (no extra queries), dropping the archive's
    own tag — on /tags/x/ every row would otherwise repeat "x" — and capping
    the count so rows stay one scan-friendly line.
    """
    for section in sections:
        for post in section["posts"]:
            tags = [t for t in post.tags.all() if t.slug != exclude_slug]
            post.row_tags = tags[:limit]


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
            context["intro_toc"] = page.toc_tree if page.show_toc else []
            featured_tags_config = page.get_featured_tags_config()
            featured_categories_config = page.get_featured_categories_config()
        except Page.DoesNotExist:
            context["intro_html"] = ""
            context["intro_toc"] = []
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
            # distinct() is required: filter(tags__in=...) joins the M2M table
            # and yields one row per matching (post, tag) pair, so a post with
            # multiple active featured tags would be appended to each bucket
            # more than once by the loop below.
            tag_posts = base_qs.filter(tags__in=active_tags).distinct()
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
            cat_posts = (
                base_qs.filter(categories__in=featured_categories)
                .prefetch_related("categories")
                .distinct()
            )
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
        show_param = self.request.GET.get("show", "")
        show_options = [opt.strip() for opt in show_param.split(",") if opt.strip()]

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

        page_obj, sections, year_strip, total = _paginate_post_index(
            self.request, posts, sort=current_sort
        )
        _attach_row_tags(sections)
        context["page_obj"] = page_obj
        context["index_sections"] = sections
        context["year_strip"] = year_strip
        context["total_posts"] = total
        context["current_sort"] = current_sort
        context["show_description"] = "description" in show_options
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
                .prefetch_related("tags")
                .order_by("-published_at")
            )
        else:
            posts = (
                Post.objects.published()
                .public()
                .filter(tags=tag)
                .select_related("author")
                .prefetch_related("tags")
                .order_by("-published_at")
            )

        page_obj, sections, year_strip, total = _paginate_post_index(
            self.request, posts
        )
        _attach_row_tags(sections, exclude_slug=tag.slug)

        # Hierarchical navigation, with post counts on every linked tag
        post_filter = _taxonomy_post_filter(user, timezone.now())
        ancestors = tag.get_ancestors()
        children = (
            tag.children.filter(is_active=True)
            .annotate(post_count=Count("posts", filter=post_filter))
            .order_by("-rank", "name")
        )

        # Get sibling tags (other children of the same parent)
        if tag.parent:
            siblings = (
                tag.parent.children.filter(is_active=True)
                .exclude(pk=tag.pk)
                .annotate(post_count=Count("posts", filter=post_filter))
                .order_by("-rank", "name")
            )
        else:
            # Root-level siblings
            siblings = (
                Tag.objects.filter(parent__isnull=True, is_active=True)
                .exclude(pk=tag.pk)
                .annotate(post_count=Count("posts", filter=post_filter))
                .order_by("-rank", "name")
            )

        context["tag"] = tag
        context["page_obj"] = page_obj
        context["index_sections"] = sections
        context["year_strip"] = year_strip
        context["total_posts"] = total
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
    - show=description
    - sort=name|count|rank (default: name)
    - group=namespace (group tags by namespace)
    """

    template_name = "posts/tag_list.html"
    seo_title = "Tags"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Parse display options from query string
        show_param = self.request.GET.get("show", "")
        show_options = [opt.strip() for opt in show_param.split(",") if opt.strip()]

        sort_by = self.request.GET.get("sort", "name")
        group_by = self.request.GET.get("group", "")

        post_filter = _taxonomy_post_filter(user, timezone.now())

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

        # Weight-scale each tag name by post count (log scale, so one giant
        # tag doesn't flatten the rest): classes tag-weight-1 … tag-weight-4.
        tags = list(tags)
        max_count = max((t.post_count for t in tags), default=0)
        for t in tags:
            if max_count > 0 and t.post_count > 0:
                ratio = math.log1p(t.post_count) / math.log1p(max_count)
                t.weight_class = 1 + round(3 * ratio)
            else:
                t.weight_class = 1

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

        # Display options: only the description line is a toggle
        context["show_description"] = "description" in show_options
        context["current_sort"] = sort_by
        context["current_group"] = group_by

        # Stats
        context["total_tags"] = len(tags)
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
                .prefetch_related("tags")
                .order_by("-published_at")
            )
        else:
            posts = (
                Post.objects.published()
                .public()
                .filter(categories=category)
                .select_related("author")
                .prefetch_related("tags")
                .order_by("-published_at")
            )

        page_obj, sections, year_strip, total = _paginate_post_index(
            self.request, posts
        )
        _attach_row_tags(sections)

        # Hierarchical navigation, with post counts on every linked category
        post_filter = _taxonomy_post_filter(user, timezone.now())
        ancestors = category.get_ancestors()
        children = category.children.annotate(
            post_count=Count("posts", filter=post_filter)
        ).order_by("name")

        if category.parent:
            siblings = (
                category.parent.children.exclude(pk=category.pk)
                .annotate(post_count=Count("posts", filter=post_filter))
                .order_by("name")
            )
        else:
            siblings = (
                Category.objects.filter(parent__isnull=True)
                .exclude(pk=category.pk)
                .annotate(post_count=Count("posts", filter=post_filter))
                .order_by("name")
            )

        context["category"] = category
        context["page_obj"] = page_obj
        context["index_sections"] = sections
        context["year_strip"] = year_strip
        context["total_posts"] = total
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
    Display all categories as an indented tree with post counts and inline
    descriptions.

    Supports query parameters:
    - sort=name|count (default: name; applies within each tree level)
    """

    template_name = "posts/category_list.html"
    seo_title = "Categories"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        sort_by = self.request.GET.get("sort", "name")

        post_filter = _taxonomy_post_filter(user, timezone.now())

        categories = Category.objects.annotate(
            post_count=Count("posts", filter=post_filter)
        ).select_related("parent")

        if sort_by == "count":
            categories = categories.order_by("-post_count", "name")
        else:
            categories = categories.order_by("name")

        # Arrange into a tree; queryset order carries into each level.
        categories = list(categories)
        by_parent = {}
        for cat in categories:
            by_parent.setdefault(cat.parent_id, []).append(cat)

        def build(parent_id):
            return [
                {"category": cat, "children": build(cat.pk)}
                for cat in by_parent.get(parent_id, [])
            ]

        context["category_tree"] = build(None)
        context["current_sort"] = sort_by
        context["total_categories"] = len(categories)
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
            context["toc_nodes"] = page.toc_tree if page.show_toc else []
            context["seo_title"] = page.title
        except Page.DoesNotExist:
            raise Http404(f"Page '{slug}' not found")

        return context


class FeedIndexView(SEOContextMixin, TemplateView):
    """Human-readable index of every syndication feed the site exposes.

    Surfaces: global, featured, per-category, and per-series feeds. Per-tag
    feeds aren't enumerated (the tag vocabulary can be large); the template
    points readers at /tags/ where each tag page already links its own feed.
    """

    template_name = "posts/feed_index.html"
    seo_title = "Feeds"
    seo_description = "RSS and Atom feeds for every section of the site — subscribe in any feed reader."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_seo_context())

        user = self.request.user
        is_staff = user.is_authenticated and (user.is_staff or user.is_superuser)

        # Categories with at least one visible post — mirrors CategoryListView.
        now = timezone.now()
        if is_staff:
            cat_post_filter = Q(posts__is_deleted=False)
            series_post_filter = Q(posts__is_deleted=False)
        else:
            cat_post_filter = Q(
                posts__is_deleted=False,
                posts__status=Post.Status.PUBLISHED,
                posts__visibility=Post.Visibility.PUBLIC,
                posts__published_at__isnull=False,
                posts__published_at__lte=now,
            )
            series_post_filter = cat_post_filter

        context["categories"] = (
            Category.objects.annotate(post_count=Count("posts", filter=cat_post_filter))
            .filter(post_count__gt=0)
            .order_by("name")
        )
        context["series_list"] = (
            Series.objects.annotate(
                post_count=Count("posts", filter=series_post_filter)
            )
            .filter(post_count__gt=0)
            .order_by("title")
        )
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

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except Http404:
            # Fall back to the slug-history table: if this slug is a former
            # slug of a post the visitor is allowed to see, 301 to its current
            # URL so renamed posts don't break inbound links.
            from .models import PostSlugHistory

            history = (
                PostSlugHistory.objects.select_related("post")
                .filter(old_slug=self.kwargs.get(self.slug_url_kwarg))
                .first()
            )
            if history and self.get_queryset().filter(pk=history.post_id).exists():
                return redirect("post-detail", slug=history.post.slug, permanent=True)
            raise

    def get_queryset(self):
        qs = Post.all_objects.select_related("author", "series").prefetch_related(
            "categories",
            "tags",
            "co_authors",
            "post_assets__asset",  # Prefetch for asset resolution in markdown
        )
        user = self.request.user
        now = timezone.now()
        if user.is_authenticated and (user.is_staff or user.is_superuser):
            # Staff can view anything (including soft-deleted for diagnostics)
            return qs
        # Public visitors: published, visible, not soft-deleted, not expired.
        return qs.filter(
            Q(expire_at__isnull=True) | Q(expire_at__gt=now),
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

        similar_sims = (
            PostSimilarity.objects.filter(
                source_post=post,
                target_post__status=Post.Status.PUBLISHED,
                target_post__is_deleted=False,
                # Unlisted posts are link-only: viewable at their URL but never
                # advertised on other pages, so only PUBLIC targets appear here.
                target_post__visibility=Post.Visibility.PUBLIC,
            )
            .select_related("target_post", "target_post__series")
            .prefetch_related("target_post__tags", "target_post__categories")
            .order_by("-score", "-target_post__published_at")[:6]
        )
        similar_posts = []
        for sim in similar_sims:
            target = sim.target_post
            target.similarity_score = sim.score
            target.similarity_components = sim.components
            similar_posts.append(target)
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

    def _current_sort(self):
        current_sort = self.request.GET.get("sort", "updated")
        if current_sort not in ("updated", "name", "count"):
            current_sort = "updated"
        return current_sort

    def get_queryset(self):
        post_filter = _taxonomy_post_filter(self.request.user, timezone.now())
        current_sort = self._current_sort()

        qs = Series.objects.annotate(
            post_count=Count("posts", filter=post_filter),
            first_published=Min("posts__published_at", filter=post_filter),
            last_published=Max("posts__published_at", filter=post_filter),
            total_reading_time=Sum("posts__reading_time_minutes", filter=post_filter),
        ).filter(post_count__gt=0)

        if current_sort == "count":
            qs = qs.order_by("-post_count", "title")
        elif current_sort == "name":
            qs = qs.order_by("title")
        else:  # updated: a series with a new entry surfaces first
            qs = qs.order_by(F("last_published").desc(nulls_last=True), "title")

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        series_list = list(context["series_list"])
        for s in series_list:
            minutes = s.total_reading_time or 0
            if minutes >= 60:
                s.reading_display = f"{minutes / 60:.1f} hr"
            elif minutes > 0:
                s.reading_display = f"{minutes} min"
            else:
                s.reading_display = ""
        context["series_list"] = series_list
        context["current_sort"] = self._current_sort()
        context["total_series"] = len(series_list)
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


# ---------------------------------------------------------------------------
# Bibliography: public library page + exports
# ---------------------------------------------------------------------------

_PUBLIC_CITATION_FILTER = Q(
    post_citations__post__is_deleted=False,
    post_citations__post__status="published",
    post_citations__post__visibility="public",
)


class LibraryView(SEOContextMixin, TemplateView):
    """
    GET /library/

    Browsable listing of every source cited in published public posts —
    a reading list for the whole site. Supports search (?q=), type and
    year filters, and links each entry to the posts citing it.
    """

    template_name = "posts/library.html"
    seo_title = "Library"
    PAGE_SIZE = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        sources = Source.objects.cited_publicly().annotate(
            cited_count=Count(
                "post_citations",
                filter=_PUBLIC_CITATION_FILTER,
                distinct=True,
            )
        )

        query = self.request.GET.get("q", "").strip()
        if query:
            from django.db.models import TextField
            from django.db.models.functions import Cast

            # authors is a JSONField — "authors__icontains" would be parsed
            # as a key transform, so cast to text for substring matching.
            sources = sources.annotate(
                authors_text=Cast("authors", TextField())
            ).filter(
                Q(title__icontains=query)
                | Q(citation_key__icontains=query)
                | Q(container_title__icontains=query)
                | Q(authors_text__icontains=query)
            )

        source_type = self.request.GET.get("type", "").strip()
        if source_type:
            sources = sources.filter(source_type=source_type)

        year = self.request.GET.get("year", "").strip()
        if year.isdigit():
            sources = sources.filter(**{"issued_date__date-parts__0__0": int(year)})

        sort = self.request.GET.get("sort", "cited")
        if sort == "title":
            sources = sources.order_by("title")
        else:
            sort = "cited"
            sources = sources.order_by("-cited_count", "title")

        sources = sources.prefetch_related(
            Prefetch(
                "post_citations",
                queryset=PostCitation.objects.filter(
                    post__is_deleted=False,
                    post__status="published",
                    post__visibility="public",
                )
                .select_related("post")
                .order_by("-post__published_at"),
                to_attr="public_citations",
            ),
            Prefetch(
                "files",
                queryset=SourceFile.objects.filter(is_public=True),
                to_attr="public_files",
            ),
        )

        paginator = Paginator(sources, self.PAGE_SIZE)
        page = paginator.get_page(self.request.GET.get("page"))

        # Facets: types present in the (unfiltered) public library
        type_facets = (
            Source.objects.cited_publicly()
            .values("source_type")
            .annotate(count=Count("id", distinct=True))
            .order_by("-count")
        )
        type_labels = dict(Source._meta.get_field("source_type").choices)

        context.update(
            {
                "page_obj": page,
                "total_sources": paginator.count,
                "query": query,
                "current_type": source_type,
                "current_year": year,
                "current_sort": sort,
                "type_facets": [
                    {
                        "value": t["source_type"],
                        "label": type_labels.get(t["source_type"], t["source_type"]),
                        "count": t["count"],
                    }
                    for t in type_facets
                ],
                "seo_description": "Every source cited across the site — "
                "a browsable reference library.",
            }
        )
        return context


def _visible_posts_for(user):
    """Post queryset mirroring PostDetailView visibility rules."""
    now = timezone.now()
    qs = Post.all_objects.all()
    if user.is_authenticated and (user.is_staff or user.is_superuser):
        return qs
    return qs.filter(
        Q(expire_at__isnull=True) | Q(expire_at__gt=now),
        is_deleted=False,
        status=Post.Status.PUBLISHED,
        visibility__in=[Post.Visibility.PUBLIC, Post.Visibility.UNLISTED],
        published_at__isnull=False,
        published_at__lte=now,
    )


def _export_response(sources, fmt, filename_base):
    from engine.bibliography.export import EXPORT_FORMATS, export_sources

    if fmt not in EXPORT_FORMATS:
        raise Http404("Unknown export format")
    content_type, extension = EXPORT_FORMATS[fmt]
    response = HttpResponse(
        export_sources(sources, fmt),
        content_type=f"{content_type}; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename_base}.{extension}"'
    )
    return response


def library_export(request, fmt):
    """GET /library/export.<fmt> — the public library in BibTeX/RIS/CSL-JSON."""
    sources = Source.objects.cited_publicly().order_by("citation_key")
    return _export_response(sources, fmt, "library")


def post_bibliography_export(request, slug, fmt):
    """GET /posts/<slug>/bibliography.<fmt> — one post's bibliography."""
    post = _visible_posts_for(request.user).filter(slug=slug).first()
    if post is None:
        raise Http404("Post not found")
    sources = list(
        Source.objects.filter(post_citations__post=post).order_by(
            "post_citations__position"
        )
    )
    if not sources:
        raise Http404("Post has no citations")
    return _export_response(sources, fmt, f"{slug}-bibliography")
