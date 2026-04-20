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


def refresh_asset_metadata(instance) -> dict:
    """Populate core file metadata on an Asset and return a structured result.

    Returns a dict with:
      - updated: list of field names whose value changed
      - skipped: list of fields that were already populated
      - errors:  list of human-readable error strings (surface to user)
    The caller is responsible for saving ``instance`` if ``updated`` is non-empty.
    """
    import mimetypes

    result = {"updated": [], "skipped": [], "errors": []}

    if not instance.file:
        result["errors"].append("Asset has no file attached.")
        return result
    if instance.status == "uploading" and instance.upload_token:
        result["errors"].append(
            "Presigned upload is still in progress; skipping metadata refresh."
        )
        return result

    def _note(field, value):
        setattr(instance, field, value)
        result["updated"].append(field)

    # MIME type
    if not instance.mime_type:
        mime_type, _ = mimetypes.guess_type(instance.file.name)
        if mime_type:
            _note("mime_type", mime_type)
        else:
            result["errors"].append(
                "Could not guess MIME type from file extension."
            )
    else:
        result["skipped"].append("mime_type")

    # File size
    if not instance.file_size:
        try:
            _note("file_size", instance.file.size)
        except Exception as exc:
            result["errors"].append(f"file_size: {exc}")
    else:
        result["skipped"].append("file_size")

    # File hash
    if not instance.file_hash:
        try:
            import hashlib

            file_obj = open_field_file(instance.file)
            file_obj.seek(0)
            _note("file_hash", hashlib.sha256(file_obj.read()).hexdigest())
            try:
                file_obj.seek(0)
            except Exception:
                pass
        except Exception as exc:
            result["errors"].append(f"file_hash: {exc}")
    else:
        result["skipped"].append("file_hash")

    # Image dimensions
    if instance.asset_type == "image":
        if not instance.width or not instance.height:
            try:
                file_obj = open_field_file(instance.file)
                with Image.open(file_obj) as img:
                    img.load()
                    w, h = img.size
                if not instance.width:
                    _note("width", w)
                if not instance.height:
                    _note("height", h)
                try:
                    file_obj.seek(0)
                except Exception:
                    pass
            except Exception as exc:
                logger.exception("Image dimension extraction failed for %s", instance.key)
                result["errors"].append(f"image dimensions: {exc}")
        else:
            result["skipped"].extend(["width", "height"])

    # Video dimensions + duration + bitrate + frame rate via ffprobe
    if instance.asset_type == "video":
        video_fields = ("width", "height", "duration", "bitrate", "frame_rate")
        if all(getattr(instance, f) for f in video_fields):
            result["skipped"].extend(video_fields)
        else:
            _extract_video_stream_metadata(instance, _note, result)

    return result


def _extract_video_stream_metadata(instance, note, result):
    """Run ffprobe and copy stream metadata onto ``instance``.

    Reports actionable errors on ``result["errors"]`` rather than swallowing.
    """
    import json
    import shutil
    import subprocess
    from datetime import timedelta
    from decimal import Decimal

    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        result["errors"].append(
            "ffprobe is not on the PATH of this process — cannot extract video metadata."
        )
        return

    # Download the R2/S3 object to a local temp file for ffprobe to read.
    try:
        cm = ensure_local_file(instance.file)
        local_path = cm.__enter__()
    except FileNotFoundError as exc:
        result["errors"].append(
            f"Could not open the source file from storage (FileNotFoundError: {exc}). "
            "The underlying R2 object may be missing."
        )
        return
    except Exception as exc:
        logger.exception("ensure_local_file failed for %s", instance.key)
        result["errors"].append(f"Could not download file from storage: {exc}")
        return

    try:
        try:
            proc = subprocess.run(
                [
                    ffprobe_bin,
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
        except subprocess.TimeoutExpired:
            result["errors"].append("ffprobe timed out after 30s.")
            return
        except Exception as exc:
            logger.exception("ffprobe invocation failed for %s", instance.key)
            result["errors"].append(f"ffprobe invocation failed: {exc}")
            return
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            pass

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().splitlines()
        snippet = stderr[-1] if stderr else f"exit {proc.returncode}"
        result["errors"].append(f"ffprobe failed: {snippet}")
        return

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        result["errors"].append(f"ffprobe output was not valid JSON: {exc}")
        return

    video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not video_streams:
        result["errors"].append("ffprobe reported no video streams in this file.")
        return

    stream = video_streams[0]
    if not instance.width and stream.get("width"):
        note("width", int(stream["width"]))
    if not instance.height and stream.get("height"):
        note("height", int(stream["height"]))
    if not instance.duration and stream.get("duration"):
        try:
            note("duration", timedelta(seconds=float(stream["duration"])))
        except (TypeError, ValueError) as exc:
            result["errors"].append(f"duration parse failed: {exc}")
    if not instance.bitrate and stream.get("bit_rate"):
        try:
            note("bitrate", int(stream["bit_rate"]) // 1000)
        except (TypeError, ValueError) as exc:
            result["errors"].append(f"bitrate parse failed: {exc}")
    if not instance.frame_rate and stream.get("r_frame_rate"):
        fr = stream["r_frame_rate"]
        if "/" in fr:
            try:
                num, den = fr.split("/")
                if float(den) != 0:
                    note("frame_rate", Decimal(str(round(float(num) / float(den), 2))))
            except (TypeError, ValueError) as exc:
                result["errors"].append(f"frame_rate parse failed: {exc}")


@receiver(post_save, sender="engine.Asset")
def populate_asset_metadata(sender, instance, created, **kwargs):
    """Signal handler that refreshes metadata and kicks off renditions on save.

    The actual extraction logic lives in ``refresh_asset_metadata`` so the admin
    action can call it directly and surface results.
    """
    result = refresh_asset_metadata(instance)
    needs_save = bool(result["updated"])

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
