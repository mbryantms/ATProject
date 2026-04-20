"""
Utility functions for the engine app, including asset rendition generation.
"""

import logging
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver
from PIL import Image

from .storage_utils import ensure_local_file, open_field_file

logger = logging.getLogger(__name__)


def generate_asset_renditions(asset, widths=None, formats=None):
    """
    Generate responsive renditions for an image asset.

    Each rendition's status moves PENDING → PROCESSING → COMPLETED (or FAILED).
    Widths and JPEG quality are read from Django settings when not overridden.

    Args:
        asset: Asset instance (must be image type)
        widths: List of widths (default: settings.ASSET_RENDITION_WIDTHS)
        formats: List of formats (default: ['auto'] - keeps original format)

    Returns:
        List of AssetRendition instances that were touched (created or refreshed).
    """
    from .models import AssetRendition

    if asset.asset_type != "image":
        return []

    if widths is None:
        widths = getattr(
            settings, "ASSET_RENDITION_WIDTHS", [400, 800, 1200, 1600]
        )
    if formats is None:
        formats = ["auto"]

    jpeg_quality = getattr(settings, "ASSET_RENDITION_JPEG_QUALITY", 85)

    touched = []

    try:
        file_obj = open_field_file(asset.file)
        with Image.open(file_obj) as img:
            img.load()
            original_width, original_height = img.size
            original_format = (img.format or "JPEG").upper()

            for width in widths:
                if width >= original_width:
                    continue

                for fmt in formats:
                    height = int((width / original_width) * original_height)
                    rendition, _ = AssetRendition.objects.get_or_create(
                        asset=asset,
                        width=width,
                        format=fmt,
                        quality="high",
                        defaults={
                            "height": height,
                            "status": AssetRendition.Status.PENDING,
                        },
                    )
                    if rendition.file and rendition.status == AssetRendition.Status.COMPLETED:
                        continue

                    rendition.status = AssetRendition.Status.PROCESSING
                    rendition.error_message = ""
                    rendition.save(update_fields=["status", "error_message"])

                    try:
                        resized_img = img.copy()
                        resized_img.thumbnail(
                            (width, height), Image.Resampling.LANCZOS
                        )

                        if fmt == "auto":
                            output_format = original_format
                            ext = output_format.lower()
                        else:
                            output_format = fmt.upper()
                            ext = fmt.lower()

                        output = BytesIO()
                        if output_format == "JPEG":
                            resized_img = resized_img.convert("RGB")
                            resized_img.save(
                                output,
                                format=output_format,
                                quality=jpeg_quality,
                                optimize=True,
                            )
                        else:
                            resized_img.save(
                                output, format=output_format, optimize=True
                            )

                        output.seek(0)
                        content = output.read()

                        filename = f"{asset.key}-{width}w.{ext}"
                        rendition.file.save(
                            filename, ContentFile(content), save=False
                        )
                        rendition.height = height
                        rendition.file_size = len(content)
                        rendition.status = AssetRendition.Status.COMPLETED
                        rendition.save()
                        touched.append(rendition)
                    except Exception as render_exc:
                        rendition.status = AssetRendition.Status.FAILED
                        rendition.error_message = str(render_exc)[:500]
                        rendition.save(
                            update_fields=["status", "error_message"]
                        )
                        logger.warning(
                            "Rendition %sw (%s) failed for asset %s: %s",
                            width,
                            fmt,
                            asset.key,
                            render_exc,
                        )

        try:
            file_obj.seek(0)
        except Exception:
            pass

    except Exception as exc:
        logger.exception(
            "Rendition pipeline aborted for asset %s: %s", asset.key, exc
        )

    return touched


@receiver(post_save, sender="engine.Asset")
def populate_asset_metadata(sender, instance, created, **kwargs):
    """
    Signal handler to populate metadata and generate renditions when asset is uploaded.
    """
    import mimetypes

    # Only process on creation or if file changed
    if not instance.file:
        return

    # Skip for presigned uploads - file doesn't exist yet
    if instance.status == "uploading" and instance.upload_token:
        return

    needs_save = False

    # Populate MIME type if missing
    if not instance.mime_type:
        mime_type, _ = mimetypes.guess_type(instance.file.name)
        if mime_type:
            instance.mime_type = mime_type
            needs_save = True

    # Populate file size if missing
    if not instance.file_size:
        try:
            instance.file_size = instance.file.size
            needs_save = True
        except Exception:
            pass

    # Calculate file hash if missing (for deduplication)
    if not instance.file_hash:
        try:
            import hashlib

            file_obj = open_field_file(instance.file)
            file_obj.seek(0)
            file_hash = hashlib.sha256(file_obj.read()).hexdigest()
            instance.file_hash = file_hash
            try:
                file_obj.seek(0)
            except Exception:
                pass
            needs_save = True
        except Exception:
            pass

    # Extract dimensions for images
    if instance.asset_type == "image" and (not instance.width or not instance.height):
        try:
            file_obj = open_field_file(instance.file)
            with Image.open(file_obj) as img:
                img.load()
                instance.width, instance.height = img.size
                needs_save = True
            try:
                file_obj.seek(0)
            except Exception:
                pass
        except Exception as e:
            print(f"Error extracting image dimensions for {instance.key}: {e}")

    # Extract dimensions for videos
    if instance.asset_type == "video" and (
        not instance.width
        or not instance.height
        or not instance.duration
        or not instance.bitrate
        or not instance.frame_rate
    ):
        try:
            import json
            import subprocess
            from datetime import timedelta
            from decimal import Decimal

            with ensure_local_file(instance.file) as local_path:
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
                    timeout=30,
                )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        if not instance.width:
                            instance.width = stream.get("width")
                            needs_save = True
                        if not instance.height:
                            instance.height = stream.get("height")
                            needs_save = True
                        if not instance.duration and stream.get("duration"):
                            duration_seconds = float(stream["duration"])
                            instance.duration = timedelta(seconds=duration_seconds)
                            needs_save = True
                        if not instance.bitrate and stream.get("bit_rate"):
                            bitrate_bps = int(stream["bit_rate"])
                            instance.bitrate = bitrate_bps // 1000
                            needs_save = True
                        if not instance.frame_rate and stream.get("r_frame_rate"):
                            frame_rate_str = stream["r_frame_rate"]
                            if "/" in frame_rate_str:
                                num, den = frame_rate_str.split("/")
                                if den != "0":
                                    frame_rate = float(num) / float(den)
                                    instance.frame_rate = Decimal(
                                        str(round(frame_rate, 2))
                                    )
                                    needs_save = True
                        break
        except FileNotFoundError:
            print(
                f"ffprobe not found - cannot extract video metadata for {instance.key}"
            )
        except Exception as e:
            print(f"Error extracting video metadata for {instance.key}: {e}")

    # Save if metadata was updated (avoid recursion by checking if we're already saving)
    if needs_save and not kwargs.get("update_fields"):
        instance.save(
            update_fields=[
                "mime_type",
                "file_size",
                "width",
                "height",
                "duration",
                "bitrate",
                "frame_rate",
                "file_hash",
            ]
        )

    # Extract extended metadata (EXIF, audio tags, etc.) - only on creation
    if created:
        metadata_enqueued = False
        try:
            # Try Celery first (async)
            from .tasks import extract_metadata_async

            try:
                extract_metadata_async.delay(instance.id)
                metadata_enqueued = True
            except Exception as exc:
                print(
                    f"Celery unavailable for metadata extraction, falling back to sync: {exc}"
                )
        except ImportError:
            pass

        if not metadata_enqueued:
            # Celery not available, extract synchronously
            try:
                from .metadata_extractor import extract_all_metadata

                extract_all_metadata(instance)
            except Exception as e:
                print(f"Error extracting metadata for {instance.key}: {e}")

    # Generate renditions for images (only on creation)
    if created and instance.asset_type == "image" and instance.status == "ready":
        # Generate renditions asynchronously if Celery is available, otherwise sync
        renditions_enqueued = False
        try:
            from .tasks import generate_renditions_async

            try:
                generate_renditions_async.delay(instance.id)
                renditions_enqueued = True
            except Exception as exc:
                print(
                    f"Celery unavailable for rendition generation, falling back to sync: {exc}"
                )
        except ImportError:
            pass

        if not renditions_enqueued:
            # Celery not available, generate synchronously
            generate_asset_renditions(instance)
