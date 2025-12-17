"""
Celery tasks for asynchronous asset processing.

These tasks handle:
- Metadata extraction (EXIF, audio tags, document info)
- Image rendition generation
- Video processing (future)

To use Celery, you need to:
1. Install celery: pip install celery redis
2. Configure celery in settings.py
3. Run celery worker: celery -A ATProject worker -l info
"""

import time

from celery import shared_task


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def slow_add(self, x: int, y: int) -> int:
    time.sleep(2)
    return x + y


@shared_task
def extract_metadata_async(asset_id):
    """
    Extract comprehensive metadata from an asset asynchronously.

    This task extracts:
    - EXIF data from images (camera settings, GPS, etc.)
    - Audio metadata (artist, album, genre, etc.)
    - Document metadata (author, subject, page count, etc.)
    - Color information from images

    Args:
        asset_id: Primary key of the Asset instance

    Returns:
        Dict with extraction results
    """
    from .metadata_extractor import extract_all_metadata
    from .models import Asset

    try:
        asset = Asset.objects.get(pk=asset_id)
    except Asset.DoesNotExist:
        return {"success": False, "error": f"Asset {asset_id} not found"}

    try:
        metadata = extract_all_metadata(asset)

        if metadata:
            return {
                "success": True,
                "asset_key": asset.key,
                "fields_extracted": _count_filled_fields(metadata),
            }
        else:
            return {
                "success": True,
                "asset_key": asset.key,
                "fields_extracted": 0,
                "message": "No metadata extracted (may be unsupported file type)",
            }

    except Exception as e:
        return {
            "success": False,
            "asset_key": asset.key,
            "error": str(e),
        }


@shared_task
def generate_renditions_async(asset_id, widths=None, formats=None):
    """
    Generate responsive image renditions asynchronously.

    Args:
        asset_id: Primary key of the Asset instance
        widths: List of widths to generate (default: [400, 800, 1200, 1600])
        formats: List of formats (default: ['auto'])

    Returns:
        Dict with generation results
    """
    from .models import Asset
    from .utils import generate_asset_renditions

    try:
        asset = Asset.objects.get(pk=asset_id)
    except Asset.DoesNotExist:
        return {"success": False, "error": f"Asset {asset_id} not found"}

    if asset.asset_type != "image":
        return {
            "success": False,
            "asset_key": asset.key,
            "error": "Asset is not an image",
        }

    try:
        renditions = generate_asset_renditions(asset, widths=widths, formats=formats)

        return {
            "success": True,
            "asset_key": asset.key,
            "renditions_generated": len(renditions),
        }

    except Exception as e:
        return {
            "success": False,
            "asset_key": asset.key,
            "error": str(e),
        }


@shared_task
def bulk_extract_metadata(asset_ids):
    """
    Extract metadata for multiple assets in bulk.

    This is useful for admin actions or migrations.

    Args:
        asset_ids: List of asset primary keys

    Returns:
        Dict with bulk extraction results
    """
    from .metadata_extractor import extract_all_metadata
    from .models import Asset

    results = {
        "total": len(asset_ids),
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    for asset_id in asset_ids:
        try:
            asset = Asset.objects.get(pk=asset_id)
            metadata = extract_all_metadata(asset)

            if metadata:
                results["successful"] += 1
            else:
                results["skipped"] += 1

        except Asset.DoesNotExist:
            results["failed"] += 1
            results["errors"].append(f"Asset {asset_id} not found")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Asset {asset_id}: {str(e)}")

    return results


@shared_task
def bulk_generate_renditions(asset_ids, widths=None, formats=None):
    """
    Generate renditions for multiple assets in bulk.

    Args:
        asset_ids: List of asset primary keys
        widths: List of widths to generate
        formats: List of formats

    Returns:
        Dict with bulk generation results
    """
    from .models import Asset
    from .utils import generate_asset_renditions

    results = {
        "total": len(asset_ids),
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "total_renditions": 0,
        "errors": [],
    }

    for asset_id in asset_ids:
        try:
            asset = Asset.objects.get(pk=asset_id)

            if asset.asset_type != "image":
                results["skipped"] += 1
                continue

            renditions = generate_asset_renditions(
                asset, widths=widths, formats=formats
            )
            results["successful"] += 1
            results["total_renditions"] += len(renditions)

        except Asset.DoesNotExist:
            results["failed"] += 1
            results["errors"].append(f"Asset {asset_id} not found")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Asset {asset_id}: {str(e)}")

    return results


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def update_post_derived_content(self, post_id: int):
    """
    Renders markdown and extracts TOC for a Post asynchronously.

    This is called after a Post is saved to offload slow processing.
    Also updates the search vector for full-text search.
    """
    from django.contrib.postgres.search import SearchVector

    from .markdown.extensions.toc_extractor import extract_toc_from_html
    from .markdown.renderer import render_markdown
    from .models import Post

    try:
        post = Post.objects.get(pk=post_id)
    except Post.DoesNotExist:
        return {"success": False, "error": f"Post {post_id} not found."}

    try:
        html = render_markdown(post.content_markdown or "")
        toc = extract_toc_from_html(html)

        # Build search vector with weighted fields:
        # A = highest weight (title)
        # B = high weight (subtitle, description)
        # C = medium weight (abstract)
        # D = lowest weight (content)
        search_vector = (
            SearchVector("title", weight="A", config="english")
            + SearchVector("subtitle", weight="B", config="english")
            + SearchVector("description", weight="B", config="english")
            + SearchVector("abstract", weight="C", config="english")
            + SearchVector("content_markdown", weight="D", config="english")
        )

        # Update fields directly to avoid re-triggering save() signals
        Post.objects.filter(pk=post_id).update(
            table_of_contents=toc,
            search_vector=search_vector,
        )

        return {
            "success": True,
            "post_id": post_id,
            "message": "TOC and search vector updated successfully.",
        }
    except Exception as e:
        return {
            "success": False,
            "post_id": post_id,
            "error": str(e),
        }


@shared_task
def rebuild_search_vectors():
    """
    Rebuild search vectors for all posts.

    Useful after migrations or bulk imports. Run via:
        python manage.py shell -c "from engine.tasks import rebuild_search_vectors; rebuild_search_vectors.delay()"

    Returns:
        Dict with rebuild results
    """
    from django.contrib.postgres.search import SearchVector

    from .models import Post

    # Build search vector with weighted fields
    search_vector = (
        SearchVector("title", weight="A", config="english")
        + SearchVector("subtitle", weight="B", config="english")
        + SearchVector("description", weight="B", config="english")
        + SearchVector("abstract", weight="C", config="english")
        + SearchVector("content_markdown", weight="D", config="english")
    )

    # Update all posts
    updated = Post.all_objects.update(search_vector=search_vector)

    return {
        "success": True,
        "posts_updated": updated,
        "message": f"Rebuilt search vectors for {updated} posts.",
    }


# Helper functions


def _count_filled_fields(metadata_instance):
    """Count how many fields have non-empty values."""
    count = 0
    fields_to_check = [
        "camera_make",
        "camera_model",
        "lens",
        "focal_length",
        "aperture",
        "shutter_speed",
        "iso",
        "captured_at",
        "latitude",
        "longitude",
        "artist",
        "album",
        "genre",
        "year",
        "track_number",
        "author",
        "subject",
        "keywords",
        "page_count",
        "dpi",
        "color_space",
        "color_profile",
        "average_color",
    ]

    for field in fields_to_check:
        value = getattr(metadata_instance, field, None)
        if value not in (None, "", [], {}):
            count += 1

    return count
