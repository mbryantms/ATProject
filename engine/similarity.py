from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Sequence, Set

from django.db.models import Q
from django.utils import timezone

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]{3,}")
MAX_TOKEN_COUNT = 700
CONTENT_SLICE_LENGTH = 8000
STOPWORDS: Set[str] = {
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
MIN_SCORE_DEFAULT = 0.18
MAX_CANDIDATE_BATCH = 200
CONTENT_VECTOR_ATTR = "_similarity_content_vector"


@dataclass
class SimilarityComponents:
    tag_score: float
    category_score: float
    series_score: float
    content_score: float
    recency_score: float

    def total(self) -> float:
        total = (
            TAG_WEIGHT * self.tag_score
            + CATEGORY_WEIGHT * self.category_score
            + SERIES_WEIGHT * self.series_score
            + CONTENT_WEIGHT * self.content_score
            + RECENCY_WEIGHT * self.recency_score
        )
        return total


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
        filters = (filters | Q(categories__in=category_ids)) if filters else Q(
            categories__in=category_ids
        )
    if post.series_id:
        filters = (filters | Q(series_id=post.series_id)) if filters else Q(
            series_id=post.series_id
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
            series_score=1.0 if post_series_id and candidate.series_id == post_series_id else 0.0,
            content_score=_cosine_similarity(post_tokens, candidate_tokens),
            recency_score=_recency_boost(post.published_at, candidate.published_at),
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
        token
        for token in TOKEN_PATTERN.findall(text.lower())
        if token not in STOPWORDS
    ]
    if len(tokens) > MAX_TOKEN_COUNT:
        return tokens[:MAX_TOKEN_COUNT]
    return tokens


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


def _recency_boost(primary: Optional[datetime], candidate: Optional[datetime]) -> float:
    if not primary or not candidate:
        return 0.0
    days = abs((primary - candidate).days)
    # Within ~180 days gets reasonable boost; beyond a year it fades out.
    if days >= 365:
        return 0.0
    return max(0.0, 1 - (days / 365))
