"""
Search views: API endpoint and search page.
"""

import hashlib
import json
from datetime import date

from django.core.cache import cache
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView
from django_ratelimit.decorators import ratelimit

from engine.mixins import SEOContextMixin

from .service import build_search_results


class SearchAPIView(View):
    """
    GET /api/v1/search/

    Public search API. Anonymous users see only PUBLIC+PUBLISHED posts;
    staff users see everything.
    """

    @method_decorator(ratelimit(key="ip", rate="60/m", method="GET", block=True))
    def get(self, request):
        q = request.GET.get("q", "").strip()
        if not q:
            return JsonResponse(
                {
                    "query": "",
                    "total": 0,
                    "results": {
                        "posts": [],
                        "tags": [],
                        "categories": [],
                        "series": [],
                        "sources": [],
                        "pages": [],
                    },
                    "facets": {
                        "tags": [],
                        "categories": [],
                        "series": [],
                        "years": [],
                        "completion_statuses": [],
                    },
                    "did_you_mean": None,
                }
            )

        # Parse filter params
        filters = {}
        tags = request.GET.get("tags")
        if tags:
            filters["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        categories = request.GET.get("categories")
        if categories:
            filters["categories"] = [
                c.strip() for c in categories.split(",") if c.strip()
            ]

        date_from = request.GET.get("date_from")
        if date_from:
            try:
                filters["date_from"] = date.fromisoformat(date_from)
            except ValueError:
                pass

        date_to = request.GET.get("date_to")
        if date_to:
            try:
                filters["date_to"] = date.fromisoformat(date_to)
            except ValueError:
                pass

        completion = request.GET.get("completion")
        if completion:
            filters["completion"] = [
                c.strip() for c in completion.split(",") if c.strip()
            ]

        year = request.GET.get("year")
        if year:
            try:
                filters["year"] = int(year)
            except ValueError, TypeError:
                pass

        sort = request.GET.get("sort", "relevance")
        if sort not in ("relevance", "date-newest", "date-oldest", "title"):
            sort = "relevance"

        try:
            limit = min(int(request.GET.get("limit", 20)), 50)
        except ValueError, TypeError:
            limit = 20

        try:
            offset = max(int(request.GET.get("offset", 0)), 0)
        except ValueError, TypeError:
            offset = 0

        # Cache key based on all params + user type
        is_staff = request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser
        )
        cache_params = json.dumps(
            {
                "q": q,
                "filters": filters,
                "sort": sort,
                "limit": limit,
                "offset": offset,
                "staff": is_staff,
            },
            sort_keys=True,
        )
        cache_key = f"search:{hashlib.md5(cache_params.encode()).hexdigest()}"

        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        results = build_search_results(
            q, filters=filters, sort=sort, limit=limit, offset=offset, user=request.user
        )

        cache.set(cache_key, results, 300)

        return JsonResponse(results)


@method_decorator(
    ratelimit(key="ip", rate="60/m", method="GET", block=True), name="dispatch"
)
class SearchPageView(SEOContextMixin, TemplateView):
    """
    GET /search/

    Server-renders initial results if ?q= is present.
    JS takes over for live search after page load.

    Rate-limited per IP: the ``?q=`` path runs the full ``build_search_results``
    pipeline (full-text + trigram fuzzy + facet aggregation) server-side, so an
    unthrottled endpoint would be an easy DoS lever. Mirrors the 60/m limit on
    :class:`SearchAPIView`.
    """

    template_name = "search.html"
    seo_title = "Search"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo_noindex"] = True
        q = self.request.GET.get("q", "").strip()
        context["query"] = q

        if q:
            sort = self.request.GET.get("sort", "relevance")
            context["search_results"] = build_search_results(
                q, sort=sort, limit=20, offset=0, user=self.request.user
            )
        else:
            context["search_results"] = None

        return context
