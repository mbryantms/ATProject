from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Q
from django.utils import timezone

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]{3,}")
MAX_TOKEN_COUNT = 700
CONTENT_SLICE_LENGTH = 8000
STOPWORDS: set[str] = {
    "a",
    "about",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}

TAG_WEIGHT = 0.4
CATEGORY_WEIGHT = 0.2
SERIES_WEIGHT = 0.35
CONTENT_WEIGHT = 0.4
RECENCY_WEIGHT = 0.1
BACKLINK_WEIGHT = 0.25
CITATION_WEIGHT = 0.15
MIN_SCORE_DEFAULT = 0.20
MAX_CANDIDATE_BATCH = 200
CONTENT_VECTOR_ATTR = "_similarity_content_vector"

BACKLINK_DIRECT_FACTOR = 0.6
BACKLINK_NEIGHBOR_FACTOR = 0.4


@dataclass
class SimilarityComponents:
    tag_score: float
    category_score: float
    series_score: float
    content_score: float
    recency_score: float
    backlink_score: float = 0.0
    citation_score: float = 0.0

    def total(self) -> float:
        total = (
            TAG_WEIGHT * self.tag_score
            + CATEGORY_WEIGHT * self.category_score
            + SERIES_WEIGHT * self.series_score
            + CONTENT_WEIGHT * self.content_score
            + RECENCY_WEIGHT * self.recency_score
            + BACKLINK_WEIGHT * self.backlink_score
            + CITATION_WEIGHT * self.citation_score
        )
        return total

    def as_dict(self) -> dict:
        return {
            "tag": round(self.tag_score, 4),
            "category": round(self.category_score, 4),
            "series": round(self.series_score, 4),
            "content": round(self.content_score, 4),
            "recency": round(self.recency_score, 4),
            "backlink": round(self.backlink_score, 4),
            "citation": round(self.citation_score, 4),
        }


def compute_similar_posts(
    post,
    *,
    limit: int = 6,
    min_score: float = MIN_SCORE_DEFAULT,
    allow_private: bool = False,
):
    """
    Return a list of posts ordered by similarity to ``post``.

    Similarity combines tag/category overlap, shared series membership,
    content cosine similarity, and a light recency boost. Results below
    ``min_score`` are discarded. Posts returned include an attribute
    ``similarity_score`` and ``similarity_components`` for inspection.
    """
    model = post.__class__
    now = timezone.now()

    visibility_filter = {}
    if not allow_private:
        visibility_filter.update(
            {
                "visibility__in": [
                    model.Visibility.PUBLIC,
                    model.Visibility.UNLISTED,
                ]
            }
        )

    candidate_queryset = (
        model.objects.filter(
            status=model.Status.PUBLISHED,
            published_at__isnull=False,
            published_at__lte=now,
            **visibility_filter,
        )
        .exclude(pk=post.pk)
        .select_related("series")
        .prefetch_related("tags", "categories")
    )

    tag_ids = {tag_id for tag_id in post.tags.values_list("id", flat=True)}
    category_ids = {cat_id for cat_id in post.categories.values_list("id", flat=True)}

    filters = None
    if tag_ids:
        filters = Q(tags__in=tag_ids)
    if category_ids:
        filters = (
            (filters | Q(categories__in=category_ids))
            if filters
            else Q(categories__in=category_ids)
        )
    if post.series_id:
        filters = (
            (filters | Q(series_id=post.series_id))
            if filters
            else Q(series_id=post.series_id)
        )

    if filters is not None:
        candidate_queryset = candidate_queryset.filter(filters).distinct()
    else:
        candidate_queryset = candidate_queryset.order_by("-published_at")

    candidates = list(candidate_queryset[:MAX_CANDIDATE_BATCH])
    if not candidates:
        return []

    post_tokens = _content_vector(post)
    post_series_id = post.series_id

    candidate_ids = [c.pk for c in candidates]
    neighbor_map = _build_neighbor_map(post.pk, candidate_ids)
    citation_map = _build_citation_map(post.pk, candidate_ids)
    post_neighbors = neighbor_map.get(post.pk, set())
    post_sources = citation_map.get(post.pk, set())

    scored = []
    for candidate in candidates:
        candidate_tokens = _content_vector(candidate)
        components = SimilarityComponents(
            tag_score=_jaccard(
                tag_ids,
                {tag.id for tag in candidate.tags.all()},
            ),
            category_score=_jaccard(
                category_ids,
                {cat.id for cat in candidate.categories.all()},
            ),
            series_score=1.0
            if post_series_id and candidate.series_id == post_series_id
            else 0.0,
            content_score=_cosine_similarity(post_tokens, candidate_tokens),
            recency_score=_recency_boost(post.published_at, candidate.published_at),
            backlink_score=_backlink_score(
                post.pk,
                candidate.pk,
                post_neighbors,
                neighbor_map.get(candidate.pk, set()),
            ),
            citation_score=_jaccard(
                post_sources,
                citation_map.get(candidate.pk, set()),
            ),
        )

        score = components.total()
        if score < min_score:
            continue

        candidate.similarity_score = round(score, 4)
        candidate.similarity_components = components
        scored.append(candidate)

    scored.sort(
        key=lambda c: (
            getattr(c, "similarity_score", 0.0),
            c.published_at or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return scored[:limit]


def _content_vector(post) -> Counter:
    cached = getattr(post, CONTENT_VECTOR_ATTR, None)
    if cached is not None:
        return cached

    text_parts = _extract_text_parts(post)
    tokens = _tokenize(" ".join(text_parts))
    vector = Counter(tokens)
    setattr(post, CONTENT_VECTOR_ATTR, vector)
    return vector


def _extract_text_parts(post) -> Sequence[str]:
    return [
        post.title or "",
        post.subtitle or "",
        post.description or "",
        post.abstract or "",
        (post.content_markdown or "")[:CONTENT_SLICE_LENGTH],
        (post.content_html_cached or "")[:CONTENT_SLICE_LENGTH],
    ]


def _tokenize(text: str) -> Sequence[str]:
    if not text:
        return []
    tokens = [
        token for token in TOKEN_PATTERN.findall(text.lower()) if token not in STOPWORDS
    ]
    if len(tokens) > MAX_TOKEN_COUNT:
        return tokens[:MAX_TOKEN_COUNT]
    return tokens


def _build_neighbor_map(post_id: int, candidate_ids: Sequence[int]) -> dict:
    """
    Return {post_id: set(neighbor_post_ids)} covering post + candidates,
    built from non-soft-deleted InternalLink rows in a single query.
    Neighbor set for a given post is its outgoing targets ∪ incoming sources.
    """
    from engine.models import InternalLink

    ids = {post_id, *candidate_ids}
    if not ids:
        return {}
    rows = InternalLink.objects.filter(
        Q(source_post_id__in=ids) | Q(target_post_id__in=ids)
    ).values_list("source_post_id", "target_post_id")
    neighbors: dict[int, set[int]] = {pid: set() for pid in ids}
    for source_id, target_id in rows:
        if source_id in neighbors:
            neighbors[source_id].add(target_id)
        if target_id in neighbors:
            neighbors[target_id].add(source_id)
    return neighbors


def _build_citation_map(post_id: int, candidate_ids: Sequence[int]) -> dict:
    """
    Return {post_id: set(source_id)} covering post + candidates, built
    from PostCitation rows in a single query.
    """
    from engine.models import PostCitation

    ids = {post_id, *candidate_ids}
    if not ids:
        return {}
    rows = PostCitation.objects.filter(post_id__in=ids).values_list(
        "post_id", "source_id"
    )
    sources: dict[int, set[int]] = {pid: set() for pid in ids}
    for pid, source_id in rows:
        sources[pid].add(source_id)
    return sources


def _backlink_score(
    post_id: int,
    candidate_id: int,
    post_neighbors: set[int],
    candidate_neighbors: set[int],
) -> float:
    """
    Combined signal: direct link presence + neighbor-set Jaccard.

    Direct bonus is 1.0 if the post and candidate link to each other in
    either direction. Neighbor Jaccard measures overlap of their wider
    link neighborhoods (friends-of-friends). Weighted 60/40 in favor of
    direct edges — human-authored links are the stronger intent signal.
    """
    direct = 1.0 if candidate_id in post_neighbors or post_id in candidate_neighbors else 0.0
    # Self-references in either set shouldn't pump the Jaccard.
    neighbor_a = post_neighbors - {post_id, candidate_id}
    neighbor_b = candidate_neighbors - {post_id, candidate_id}
    neighbor = _jaccard(neighbor_a, neighbor_b)
    return BACKLINK_DIRECT_FACTOR * direct + BACKLINK_NEIGHBOR_FACTOR * neighbor


def _jaccard(a_ids: Iterable[int], b_ids: Iterable[int]) -> float:
    set_a = set(a_ids)
    set_b = set(b_ids)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    if not intersection:
        return 0.0
    union = set_a | set_b
    return len(intersection) / len(union)


def _cosine_similarity(vec_a: Counter, vec_b: Counter) -> float:
    if not vec_a or not vec_b:
        return 0.0
    intersection = vec_a.keys() & vec_b.keys()
    if not intersection:
        return 0.0
    dot = sum(vec_a[token] * vec_b[token] for token in intersection)
    norm_a = math.sqrt(sum(count * count for count in vec_a.values()))
    norm_b = math.sqrt(sum(count * count for count in vec_b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _recency_boost(primary: datetime | None, candidate: datetime | None) -> float:
    if not primary or not candidate:
        return 0.0
    days = abs((primary - candidate).days)
    # Within ~180 days gets reasonable boost; beyond a year it fades out.
    if days >= 365:
        return 0.0
    return max(0.0, 1 - (days / 365))
