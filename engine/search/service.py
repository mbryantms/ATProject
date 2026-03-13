"""
Core search logic.

Provides full-text search, fuzzy matching, tag/page search, and faceted filtering.
"""

import re

from django.contrib.postgres.search import (
    SearchHeadline,
    SearchQuery,
    SearchRank,
    TrigramSimilarity,
)
from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce, ExtractYear, NullIf

from engine.models import Category, Page, Post, Tag

from .parser import parse_query, resolve_tag_aliases

# Patterns to strip residual markdown/Pandoc syntax from snippets.
# Applied only when content_html_cached is empty and raw markdown is used.
_MD_CLEANUP = [
    (re.compile(r"\{\.[\w-]+\}"), ""),  # Pandoc attributes: {.class-name}
    (re.compile(r"\{#[\w-]+\}"), ""),  # Pandoc id attrs: {#id-name}
    (re.compile(r"\{[^}]*\}"), ""),  # Any remaining brace attributes
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),  # [text](url) → text
    (re.compile(r"\[([^\]]*)\]"), r"\1"),  # [text] → text (ref links)
    (re.compile(r"[*_]{1,3}([^*_]+)[*_]{1,3}"), r"\1"),  # bold/italic
    (re.compile(r"`([^`]+)`"), r"\1"),  # inline code
    (re.compile(r"#{1,6}\s+"), ""),  # headings
    (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),  # list markers
    (re.compile(r"^\s*\d+\.\s+", re.MULTILINE), ""),  # ordered list markers
    (re.compile(r"\s{2,}"), " "),  # collapse whitespace
]


def _clean_snippet(snippet):
    """Strip markdown syntax and sanitize HTML from a snippet, preserving <mark> tags."""
    if not snippet:
        return snippet
    # Sanitize: allow only <mark> tags (from SearchHeadline) to prevent XSS
    # when the snippet source is raw markdown rather than pre-sanitized HTML.
    import nh3

    snippet = nh3.clean(snippet, tags={"mark"}, attributes={}, link_rel=None)
    for pattern, replacement in _MD_CLEANUP:
        snippet = pattern.sub(replacement, snippet)
    return snippet.strip()


def _base_post_queryset(user=None):
    """Return base queryset respecting visibility rules."""
    if user and user.is_authenticated and (user.is_staff or user.is_superuser):
        return (
            Post.all_objects.filter(is_deleted=False)
            .select_related("author")
            .prefetch_related("tags", "categories")
        )
    return (
        Post.objects.published()
        .public()
        .select_related("author")
        .prefetch_related("tags", "categories")
    )


def search_posts(
    parsed_query, filters=None, sort="relevance", limit=20, offset=0, user=None
):
    """
    Full-text search against Post.search_vector.

    Returns (queryset, total_count) where queryset is annotated with rank and snippet.
    """
    filters = filters or {}
    qs = _base_post_queryset(user)

    has_fulltext = bool(parsed_query.fulltext_query.strip())

    if has_fulltext:
        query = SearchQuery(
            parsed_query.fulltext_query,
            search_type="websearch",
            config="english",
        )
        qs = qs.filter(search_vector=query)
        # Prefer rendered HTML for clean snippets; fall back to raw markdown
        # if content_html_cached is empty (not yet rendered by Celery).
        snippet_source = Coalesce(
            NullIf("content_html_cached", Value("")),
            "content_markdown",
        )
        qs = qs.annotate(
            rank=SearchRank("search_vector", query),
            snippet=SearchHeadline(
                snippet_source,
                query,
                config="english",
                start_sel="<mark>",
                stop_sel="</mark>",
                max_words=35,
                min_words=15,
                max_fragments=3,
            ),
        )
    else:
        qs = qs.annotate(
            rank=Value(0.0),
            snippet=Value(""),
        )

    # Apply field-scoped filters from parsed query
    if parsed_query.title_filters:
        title_q = Q()
        for t in parsed_query.title_filters:
            title_q |= Q(title__icontains=t)
        qs = qs.filter(title_q)

    if parsed_query.tag_filters:
        tag_slugs = resolve_tag_aliases(parsed_query.tag_filters)
        if tag_slugs:
            qs = qs.filter(tags__slug__in=tag_slugs)

    if parsed_query.category_filters:
        cat_q = Q()
        for c in parsed_query.category_filters:
            cat_q |= Q(categories__name__iexact=c) | Q(categories__slug__iexact=c)
        qs = qs.filter(cat_q)

    if parsed_query.series_filters:
        series_q = Q()
        for s in parsed_query.series_filters:
            series_q |= Q(series__title__icontains=s) | Q(series__slug__iexact=s)
        qs = qs.filter(series_q)

    if parsed_query.author_filters:
        author_q = Q()
        for a in parsed_query.author_filters:
            author_q |= (
                Q(author__username__icontains=a)
                | Q(author__first_name__icontains=a)
                | Q(author__last_name__icontains=a)
            )
        qs = qs.filter(author_q)

    # Apply additional filters from query params
    if filters.get("tags"):
        qs = qs.filter(tags__slug__in=filters["tags"])

    if filters.get("categories"):
        qs = qs.filter(categories__slug__in=filters["categories"])

    if filters.get("date_from"):
        qs = qs.filter(published_at__gte=filters["date_from"])

    if filters.get("date_to"):
        qs = qs.filter(published_at__lte=filters["date_to"])

    if filters.get("completion"):
        qs = qs.filter(completion_status__in=filters["completion"])

    if filters.get("year"):
        qs = qs.filter(published_at__year=filters["year"])

    qs = qs.distinct()

    # Sorting
    if sort == "date-newest":
        qs = qs.order_by("-published_at")
    elif sort == "date-oldest":
        qs = qs.order_by("published_at")
    elif sort == "title":
        qs = qs.order_by("title")
    else:
        # Relevance (default)
        if has_fulltext:
            qs = qs.order_by("-rank", "-published_at")
        else:
            qs = qs.order_by("-published_at")

    total = qs.count()
    results = qs[offset : offset + limit]

    return results, total, qs


def search_posts_fuzzy(query_str, limit=5, user=None):
    """
    Fuzzy search fallback using trigram similarity on title.

    Used when full-text search returns 0 results.
    """
    if not query_str or not query_str.strip():
        return Post.objects.none(), None

    qs = _base_post_queryset(user)
    qs = (
        qs.annotate(similarity=TrigramSimilarity("title", query_str))
        .filter(similarity__gt=0.15)
        .order_by("-similarity")[:limit]
    )

    results = list(qs)
    did_you_mean = results[0].title if results else None
    return results, did_you_mean


def search_tags(query_str, limit=5):
    """Search active tags by name, including aliases."""
    if not query_str or not query_str.strip():
        return Tag.objects.none()

    qs = (
        Tag.objects.active()
        .annotate(similarity=TrigramSimilarity("name", query_str))
        .filter(Q(name__icontains=query_str) | Q(similarity__gt=0.3))
        .annotate(post_count=Count("posts"))
        .order_by("-similarity", "-usage_count")[:limit]
    )

    return qs


def search_pages(query_str, limit=3):
    """Search active pages by title and content."""
    if not query_str or not query_str.strip():
        return Page.objects.none()

    return Page.objects.filter(is_active=True).filter(
        Q(title__icontains=query_str) | Q(content__icontains=query_str)
    )[:limit]


def get_facets(base_queryset):
    """Aggregate facets from a filtered post queryset."""
    # Tags: top 15 by count
    tags = (
        Tag.objects.active()
        .filter(posts__in=base_queryset)
        .annotate(count=Count("posts", filter=Q(posts__in=base_queryset)))
        .filter(count__gt=0)
        .order_by("-count")[:15]
    )

    # Categories with counts
    categories = (
        Category.objects.filter(posts__in=base_queryset)
        .annotate(count=Count("posts", filter=Q(posts__in=base_queryset)))
        .filter(count__gt=0)
        .order_by("-count")
    )

    # Years from published_at
    years = (
        base_queryset.filter(published_at__isnull=False)
        .annotate(year=ExtractYear("published_at"))
        .values("year")
        .annotate(count=Count("id"))
        .order_by("-year")
    )

    # Completion statuses with counts
    completion_statuses = (
        base_queryset.values("completion_status")
        .annotate(count=Count("id"))
        .filter(count__gt=0)
        .order_by("-count")
    )

    return {
        "tags": [{"name": t.name, "slug": t.slug, "count": t.count} for t in tags],
        "categories": [
            {"name": c.name, "slug": c.slug, "count": c.count} for c in categories
        ],
        "years": [{"year": y["year"], "count": y["count"]} for y in years],
        "completion_statuses": [
            {"status": cs["completion_status"], "count": cs["count"]}
            for cs in completion_statuses
        ],
    }


def build_search_results(
    query_string, filters=None, sort="relevance", limit=20, offset=0, user=None
):
    """
    Orchestrator: parses query, runs all sub-searches, assembles response dict.

    Falls back to fuzzy search if full-text returns 0 posts.
    """
    parsed = parse_query(query_string)

    if parsed.is_empty and not filters:
        return {
            "query": query_string,
            "total": 0,
            "results": {"posts": [], "tags": [], "pages": []},
            "facets": {
                "tags": [],
                "categories": [],
                "years": [],
                "completion_statuses": [],
            },
            "did_you_mean": None,
        }

    # Run post search
    post_results, total, unsliced_qs = search_posts(
        parsed, filters, sort, limit, offset, user
    )

    did_you_mean = None
    fuzzy_results = []

    # If no full-text results, try fuzzy fallback
    if total == 0 and parsed.fulltext_query.strip():
        fuzzy_results, did_you_mean = search_posts_fuzzy(
            parsed.fulltext_query, limit=5, user=user
        )

    # Build post data
    posts_data = []
    source = fuzzy_results if (total == 0 and fuzzy_results) else post_results
    for post in source:
        post_data = {
            "title": post.title,
            "slug": post.slug,
            "url": post.get_absolute_url(),
            "snippet": _clean_snippet(getattr(post, "snippet", "")),
            "published_at": (
                post.published_at.isoformat() if post.published_at else None
            ),
            "tags": [{"name": t.name, "slug": t.slug} for t in post.tags.all()],
            "categories": [
                {"name": c.name, "slug": c.slug} for c in post.categories.all()
            ],
            "completion_status": post.completion_status,
            "reading_time": post.reading_time_minutes,
            "rank": round(float(getattr(post, "rank", 0)), 4),
        }
        posts_data.append(post_data)

    # Search tags and pages (only for first page)
    raw_query = parsed.fulltext_query.strip() or query_string.strip()
    tags_data = []
    pages_data = []
    if offset == 0 and raw_query:
        for tag in search_tags(raw_query, limit=5):
            tags_data.append(
                {
                    "name": tag.name,
                    "slug": tag.slug,
                    "url": f"/tags/{tag.slug}/",
                    "description": tag.description[:200] if tag.description else "",
                    "post_count": getattr(tag, "post_count", tag.usage_count),
                }
            )

        for page in search_pages(raw_query, limit=3):
            pages_data.append(
                {
                    "title": page.title or page.slug,
                    "slug": page.slug,
                    "url": f"/{page.slug}/",
                }
            )

    # Get facets from the base queryset (before pagination)
    facets = {"tags": [], "categories": [], "years": [], "completion_statuses": []}
    if total > 0:
        facets = get_facets(unsliced_qs)

    return {
        "query": query_string,
        "total": total if total > 0 else len(fuzzy_results),
        "results": {
            "posts": posts_data,
            "tags": tags_data,
            "pages": pages_data,
        },
        "facets": facets,
        "did_you_mean": did_you_mean,
    }
