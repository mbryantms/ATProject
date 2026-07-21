"""
PostCitation record sync.

Reconciles the PostCitation join table against the citations actually
resolved during rendering (the citation escaper → Pandoc → citation_renderer
pipeline reports them via ``resolved_citations``).
"""

import logging

logger = logging.getLogger(__name__)


def update_post_citations(post, resolved_citations: list[dict]) -> dict:
    """
    Sync PostCitation records to match the citations found in content.

    Args:
        post: Post instance.
        resolved_citations: List of dicts with "key" and "position" from rendering.

    Returns:
        Stats dict with created, deleted, unchanged counts.
    """
    from engine.models import PostCitation, Source

    if not resolved_citations:
        # No citations — delete all existing records
        deleted_count, _ = PostCitation.objects.filter(post=post).delete()
        return {"created": 0, "deleted": deleted_count, "unchanged": 0}

    # Get source objects for all cited keys
    cited_keys = [c["key"] for c in resolved_citations]
    sources_by_key = {
        s.citation_key: s for s in Source.objects.filter(citation_key__in=cited_keys)
    }

    # Build the desired state
    desired = {}
    for citation_data in resolved_citations:
        key = citation_data["key"]
        if key in sources_by_key:
            desired[sources_by_key[key].pk] = citation_data["position"]

    # Get current state
    existing = {
        pc.source_id: pc
        for pc in PostCitation.objects.filter(post=post).select_related("source")
    }

    created = 0
    deleted = 0
    unchanged = 0

    # Create new, update positions
    for source_pk, position in desired.items():
        if source_pk in existing:
            pc = existing[source_pk]
            if pc.position != position:
                pc.position = position
                pc.save(update_fields=["position", "updated_at"])
            unchanged += 1
        else:
            PostCitation.objects.create(
                post=post,
                source_id=source_pk,
                position=position,
            )
            created += 1

    # Delete citations no longer in content
    to_delete = set(existing.keys()) - set(desired.keys())
    if to_delete:
        deleted, _ = PostCitation.objects.filter(
            post=post, source_id__in=to_delete
        ).delete()

    return {"created": created, "deleted": deleted, "unchanged": unchanged}
