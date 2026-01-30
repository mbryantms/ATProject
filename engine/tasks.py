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
            content_html_cached=html,
        )

        return {
            "success": True,
            "post_id": post_id,
            "message": "TOC, search vector, and cached HTML updated successfully.",
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


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def finalize_presigned_upload(self, asset_id):
    """
    Process a directly-uploaded file after presigned upload confirmation.

    This task:
    - Verifies file exists in R2
    - Extracts dimensions (PIL for images, ffprobe for video)
    - Calculates file hash for deduplication
    - Calls extract_all_metadata()
    - Generates renditions for images
    - Sets status to 'ready'

    Args:
        asset_id: Primary key of the Asset instance

    Returns:
        Dict with processing results
    """
    from .metadata_extractor import extract_all_metadata
    from .models import Asset
    from .utils import generate_asset_renditions

    try:
        asset = Asset.all_objects.get(pk=asset_id)
    except Asset.DoesNotExist:
        return {"success": False, "error": f"Asset {asset_id} not found"}

    if asset.status != "processing":
        return {
            "success": False,
            "error": f"Asset {asset_id} is not in processing state (current: {asset.status})",
        }

    try:
        # Verify file exists in R2
        from .api.presigned import verify_object_exists

        result = verify_object_exists(asset.file.name)
        if not result.get("exists"):
            asset.status = "failed"
            asset.save(update_fields=["status"])
            return {"success": False, "error": "File not found in storage"}

        # Update file size from actual storage
        if result.get("size"):
            asset.file_size = result["size"]

        # Extract dimensions and other metadata based on asset type
        if asset.asset_type == "image":
            _extract_image_dimensions(asset)
        elif asset.asset_type == "video":
            _extract_video_metadata(asset)

        # Calculate file hash for deduplication
        _calculate_file_hash(asset)

        # Save dimension/hash updates
        asset.save(
            update_fields=[
                "file_size",
                "width",
                "height",
                "duration",
                "bitrate",
                "frame_rate",
                "file_hash",
            ]
        )

        # Extract extended metadata (EXIF, audio tags, etc.)
        try:
            extract_all_metadata(asset)
        except Exception as e:
            # Log but don't fail the whole task for metadata extraction issues
            import logging

            logging.getLogger(__name__).warning(
                f"Metadata extraction failed for {asset.key}: {e}"
            )

        # Generate renditions for images
        if asset.asset_type == "image":
            try:
                renditions = generate_asset_renditions(asset)
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Rendition generation failed for {asset.key}: {e}"
                )

        # Mark as ready
        asset.status = "ready"
        asset.save(update_fields=["status"])

        return {
            "success": True,
            "asset_id": asset.pk,
            "asset_key": asset.key,
            "status": "ready",
        }

    except Exception as e:
        # Mark asset as failed
        try:
            asset.status = "failed"
            asset.save(update_fields=["status"])
        except Exception:
            pass

        return {
            "success": False,
            "asset_id": asset_id,
            "error": str(e),
        }


def _extract_image_dimensions(asset):
    """Extract width and height from an image asset."""
    from PIL import Image

    from .storage_utils import open_field_file

    if asset.width and asset.height:
        return

    try:
        file_obj = open_field_file(asset.file)
        with Image.open(file_obj) as img:
            img.load()
            asset.width, asset.height = img.size
        try:
            file_obj.seek(0)
        except Exception:
            pass
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(
            f"Failed to extract image dimensions for {asset.key}: {e}"
        )


def _extract_video_metadata(asset):
    """Extract dimensions, duration, bitrate, and frame rate from video."""
    import json
    import subprocess
    from datetime import timedelta
    from decimal import Decimal

    from .storage_utils import ensure_local_file

    try:
        with ensure_local_file(asset.file) as local_path:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_streams",
                    local_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    if not asset.width:
                        asset.width = stream.get("width")
                    if not asset.height:
                        asset.height = stream.get("height")
                    if not asset.duration and stream.get("duration"):
                        duration_seconds = float(stream["duration"])
                        asset.duration = timedelta(seconds=duration_seconds)
                    if not asset.bitrate and stream.get("bit_rate"):
                        bitrate_bps = int(stream["bit_rate"])
                        asset.bitrate = bitrate_bps // 1000
                    if not asset.frame_rate and stream.get("r_frame_rate"):
                        frame_rate_str = stream["r_frame_rate"]
                        if "/" in frame_rate_str:
                            num, den = frame_rate_str.split("/")
                            if den != "0":
                                frame_rate = float(num) / float(den)
                                asset.frame_rate = Decimal(str(round(frame_rate, 2)))
                    break
    except FileNotFoundError:
        import logging

        logging.getLogger(__name__).warning(
            f"ffprobe not found - cannot extract video metadata for {asset.key}"
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(
            f"Failed to extract video metadata for {asset.key}: {e}"
        )


def _calculate_file_hash(asset):
    """Calculate SHA256 hash of asset file."""
    import hashlib

    from .storage_utils import open_field_file

    if asset.file_hash:
        return

    try:
        file_obj = open_field_file(asset.file)
        file_obj.seek(0)
        file_hash = hashlib.sha256(file_obj.read()).hexdigest()
        asset.file_hash = file_hash
        try:
            file_obj.seek(0)
        except Exception:
            pass
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(
            f"Failed to calculate file hash for {asset.key}: {e}"
        )


@shared_task
def cleanup_expired_uploads():
    """
    Delete Assets stuck in 'uploading' state past their expiry time.

    This task should be run periodically (e.g., hourly via Celery Beat) to clean up
    failed or abandoned presigned uploads.

    Returns:
        Dict with cleanup results
    """
    from django.utils import timezone

    from .models import Asset

    now = timezone.now()

    # Find expired uploads
    expired_assets = Asset.all_objects.filter(
        status="uploading",
        upload_expires_at__lt=now,
    )

    count = expired_assets.count()
    asset_ids = list(expired_assets.values_list("id", flat=True))

    # Delete expired assets
    expired_assets.delete()

    return {
        "success": True,
        "cleaned_up": count,
        "asset_ids": asset_ids,
    }


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 2},
)
def cleanup_orphaned_assets(
    self,
    delete_files: bool = False,
    include_soft_deleted: bool = True,
    days_old: int = 30,
    cleanup_renditions: bool = True,
    cleanup_unused: bool = True,
):
    """
    Clean up orphaned renditions and unused assets.

    This task can be scheduled via django-celery-beat to run periodically
    (e.g., weekly) to prevent accumulation of orphaned files.

    Args:
        delete_files: If True, also delete files from R2 storage (default: False)
        include_soft_deleted: Target soft-deleted assets (default: True)
        days_old: Only delete items older than N days (default: 30)
        cleanup_renditions: Clean up orphaned renditions (default: True)
        cleanup_unused: Clean up unused assets (default: True)

    Returns:
        Dict with cleanup results

    Schedule via django-celery-beat admin:
        Task: engine.tasks.cleanup_orphaned_assets
        Schedule: Weekly (crontab: 0 3 * * 0 for Sunday 3am)
        Kwargs: {"delete_files": true, "days_old": 30}
    """
    from datetime import timedelta

    from django.db.models import Count
    from django.utils import timezone

    from .models import Asset, AssetRendition

    results = {
        "success": True,
        "orphaned_renditions": {"found": 0, "deleted": 0, "files_deleted": 0},
        "unused_assets": {"found": 0, "deleted": 0, "files_deleted": 0},
        "total_size_freed": 0,
        "errors": [],
    }

    cutoff_date = timezone.now() - timedelta(days=days_old)

    # --- Clean up orphaned renditions ---
    if cleanup_renditions:
        try:
            if include_soft_deleted:
                # Renditions of soft-deleted assets
                orphaned_renditions = AssetRendition.objects.filter(
                    asset__is_deleted=True,
                    created_at__lt=cutoff_date,
                )
            else:
                # Truly orphaned (asset doesn't exist)
                all_renditions = AssetRendition.objects.filter(created_at__lt=cutoff_date)
                valid_asset_ids = Asset.all_objects.values_list("id", flat=True)
                orphaned_renditions = all_renditions.exclude(asset_id__in=valid_asset_ids)

            results["orphaned_renditions"]["found"] = orphaned_renditions.count()

            # Calculate size
            total_rendition_size = sum(r.file_size or 0 for r in orphaned_renditions)
            results["total_size_freed"] += total_rendition_size

            # Delete files from R2 first
            if delete_files:
                for rendition in orphaned_renditions:
                    if rendition.file:
                        try:
                            rendition.file.delete(save=False)
                            results["orphaned_renditions"]["files_deleted"] += 1
                        except Exception as e:
                            results["errors"].append(
                                f"Failed to delete rendition file: {e}"
                            )

            # Delete DB records
            deleted_count, _ = orphaned_renditions.delete()
            results["orphaned_renditions"]["deleted"] = deleted_count

        except Exception as e:
            results["errors"].append(f"Rendition cleanup error: {e}")

    # --- Clean up unused assets ---
    if cleanup_unused:
        try:
            if include_soft_deleted:
                # Soft-deleted assets not used in posts
                queryset = Asset.all_objects.filter(
                    is_deleted=True,
                    created_at__lt=cutoff_date,
                )
            else:
                # Active unused assets (be careful with this!)
                queryset = Asset.objects.filter(created_at__lt=cutoff_date)

            unused_assets = queryset.annotate(post_count=Count("postasset")).filter(
                post_count=0
            )

            results["unused_assets"]["found"] = unused_assets.count()

            # Calculate size
            total_asset_size = sum(a.file_size or 0 for a in unused_assets)
            results["total_size_freed"] += total_asset_size

            # Delete files from R2 first
            if delete_files:
                for asset in unused_assets:
                    # Delete rendition files
                    for rendition in asset.renditions.all():
                        if rendition.file:
                            try:
                                rendition.file.delete(save=False)
                            except Exception as e:
                                results["errors"].append(
                                    f"Failed to delete rendition file for {asset.key}: {e}"
                                )

                    # Delete asset file
                    if asset.file:
                        try:
                            asset.file.delete(save=False)
                            results["unused_assets"]["files_deleted"] += 1
                        except Exception as e:
                            results["errors"].append(
                                f"Failed to delete asset file {asset.key}: {e}"
                            )

            # Delete DB records
            deleted_count, details = unused_assets.delete()
            results["unused_assets"]["deleted"] = deleted_count

        except Exception as e:
            results["errors"].append(f"Unused asset cleanup error: {e}")

    # Format size for readability
    results["total_size_freed_human"] = _format_bytes(results["total_size_freed"])

    return results


def _format_bytes(size_bytes):
    """Format bytes as human-readable size."""
    if size_bytes == 0:
        return "0 B"

    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0

    return f"{size_bytes:.2f} TB"


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
