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


# Ordered by descending "modern-ness": the image enhancer emits <source> tags
# in this order so browsers pick the best format they understand. Each tuple
# is (rendition tag stored in AssetRendition.format, PIL save format, file
# extension, mime type). "auto" means "preserve the source's native format".
_MODERN_FORMATS = (
    ("avif", "AVIF", "avif", "image/avif"),
    ("webp", "WEBP", "webp", "image/webp"),
)
_SOURCE_FORMAT_TAG = "auto"


# Social-share crops. Each entry is (preset name, width, height). When the
# source is large enough, these get cropped (using focal point when set,
# else centered) and re-encoded at that exact aspect ratio — ideal for
# og:image, Twitter card, and card thumbnails where the browser needs a
# fixed-ratio image, not a down-scaled copy of the original.
_SOCIAL_CROPS = (
    ("social-wide", 1200, 630),  # 1.905:1 — Facebook / Twitter summary_large_image
    ("social-square", 1200, 1200),  # 1:1 — Instagram-style cards, Mastodon
)


def _format_mime(fmt_tag: str, source_pil_format: str) -> str:
    """Return the MIME type we should advertise for a rendition."""
    if fmt_tag == "avif":
        return "image/avif"
    if fmt_tag == "webp":
        return "image/webp"
    # Source format
    return {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }.get((source_pil_format or "").upper(), "image/jpeg")


def _save_to_bytes(img, pil_format: str, *, jpeg_quality: int) -> bytes:
    """Encode ``img`` to ``pil_format`` bytes with format-appropriate options.

    Keeps alpha for formats that support it; converts to RGB only for JPEG.
    """
    buf = BytesIO()
    pil_format = pil_format.upper()
    if pil_format == "JPEG":
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(
            buf,
            format="JPEG",
            quality=jpeg_quality,
            optimize=True,
            progressive=True,
        )
    elif pil_format == "WEBP":
        img.save(buf, format="WEBP", quality=80, method=6)
    elif pil_format == "AVIF":
        # Pillow's AVIF plugin: quality 60 ≈ JPEG 85 visually; speed 6 is
        # a reasonable encoding-time vs compression trade-off.
        img.save(buf, format="AVIF", quality=60, speed=6)
    elif pil_format == "PNG":
        img.save(buf, format="PNG", optimize=True)
    else:
        img.save(buf, format=pil_format, optimize=True)
    return buf.getvalue()


def _compute_focal_crop_box(
    src_w: int, src_h: int, target_w: int, target_h: int, focal_x: float, focal_y: float
) -> tuple[int, int, int, int]:
    """Compute the crop box that preserves the target aspect ratio while
    keeping the focal point in view. Returns (left, upper, right, lower).
    """
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if abs(src_ratio - target_ratio) < 1e-3:
        return (0, 0, src_w, src_h)

    if src_ratio > target_ratio:
        # Source is wider than target — crop horizontally.
        crop_w = int(src_h * target_ratio)
        crop_h = src_h
        focal_px = focal_x * src_w
        left = max(0, min(src_w - crop_w, int(focal_px - crop_w / 2)))
        upper = 0
    else:
        # Source is taller than target — crop vertically.
        crop_w = src_w
        crop_h = int(src_w / target_ratio)
        focal_py = focal_y * src_h
        left = 0
        upper = max(0, min(src_h - crop_h, int(focal_py - crop_h / 2)))
    return (left, upper, left + crop_w, upper + crop_h)


def _supported_modern_formats() -> tuple[tuple[str, str, str, str], ...]:
    """Return the subset of _MODERN_FORMATS this Pillow install can emit.

    If AVIF isn't compiled in (older Pillow / alternate base image), drop it
    and carry on with WebP + source — better than crashing every rendition.
    """
    from PIL import features

    return tuple(
        entry
        for entry in _MODERN_FORMATS
        if entry[0] != "avif" or features.check("avif")
    )


def _animated_frames(img):
    """Yield (frame_image, duration_ms) tuples from an animated PIL Image.

    Each frame is copied to an RGBA image so downstream encoders don't see
    palette mutations from PIL's frame iteration.
    """
    from PIL import ImageSequence

    for frame in ImageSequence.Iterator(img):
        duration = frame.info.get("duration", 100)
        yield frame.convert("RGBA"), duration


def _generate_animated_renditions(*, asset, img, widths, jpeg_quality):
    """Build animated WebP (and AVIF when supported) renditions for a GIF.

    An animated GIF is often the largest single asset on a page; converting
    to animated WebP typically cuts its weight by 4-10×. We keep the
    original source format (`"auto"`) untouched so ancient clients still
    have a fallback.
    """
    from PIL import features

    from .models import AssetRendition

    touched = []
    frames = list(_animated_frames(img))
    if not frames:
        return touched

    original_width, original_height = img.size
    loop = img.info.get("loop", 0)

    modern_targets = [("webp", "WEBP", "webp")]
    if features.check("avif"):
        modern_targets.append(("avif", "AVIF", "avif"))
    modern_targets.append((_SOURCE_FORMAT_TAG, "GIF", "gif"))

    for width in widths:
        if width >= original_width:
            continue
        height = int((width / original_width) * original_height)

        resized_frames = [
            (frame.copy().resize((width, height), Image.Resampling.LANCZOS), dur)
            for frame, dur in frames
        ]

        for fmt_tag, pil_format, ext in modern_targets:
            rendition, _ = AssetRendition.objects.get_or_create(
                asset=asset,
                width=width,
                format=fmt_tag,
                quality=AssetRendition.Quality.HIGH,
                defaults={
                    "height": height,
                    "preset": "",
                    "status": AssetRendition.Status.PENDING,
                    "file_size": 0,
                },
            )
            if (
                rendition.file
                and rendition.status == AssetRendition.Status.COMPLETED
                and rendition.preset == ""
            ):
                continue

            rendition.status = AssetRendition.Status.PROCESSING
            rendition.error_message = ""
            rendition.preset = ""
            rendition.save(update_fields=["status", "error_message", "preset"])

            try:
                buf = BytesIO()
                first, *rest = [f for f, _ in resized_frames]
                durations = [d for _, d in resized_frames]
                save_kwargs = {
                    "format": pil_format,
                    "save_all": True,
                    "append_images": rest,
                    "duration": durations,
                    "loop": loop,
                }
                if pil_format == "WEBP":
                    save_kwargs["quality"] = 80
                    save_kwargs["method"] = 6
                elif pil_format == "AVIF":
                    save_kwargs["quality"] = 60
                    save_kwargs["speed"] = 6
                elif pil_format == "GIF":
                    save_kwargs["optimize"] = True
                    save_kwargs["disposal"] = 2
                first.save(buf, **save_kwargs)
                content = buf.getvalue()
            except Exception as exc:
                rendition.status = AssetRendition.Status.FAILED
                rendition.error_message = str(exc)[:500]
                rendition.save(update_fields=["status", "error_message"])
                logger.warning(
                    "Animated rendition %sw %s failed for asset %s: %s",
                    width,
                    fmt_tag,
                    asset.key,
                    exc,
                )
                continue

            filename = f"{asset.key}-{width}w.{ext}"
            rendition.file.save(filename, ContentFile(content), save=False)
            rendition.height = height
            rendition.file_size = len(content)
            rendition.is_webp = fmt_tag == "webp"
            rendition.status = AssetRendition.Status.COMPLETED
            rendition.save()
            touched.append(rendition)

    return touched


def generate_asset_renditions(asset, widths=None, formats=None):
    """Generate responsive renditions for an image asset.

    For each width, emits one rendition in each supported modern format
    (AVIF + WebP) plus one in the source's native format. The image enhancer
    serves them via a <picture> element so browsers pick the best one they
    understand.

    Also emits cropped "social" renditions (1200x630, 1200x1200) so OG /
    Twitter / card previews never ship a full-res original.

    Each rendition's status moves PENDING → PROCESSING → COMPLETED (or FAILED).
    Animated GIFs are skipped (thumbnail() doesn't preserve frames).

    Args:
        asset: Asset instance (must be image type)
        widths: List of widths (default: settings.ASSET_RENDITION_WIDTHS)
        formats: Optional override; if omitted, the full modern+source set is
            emitted. Pass a list of tags (e.g. ["auto"]) to force legacy
            behavior in tests.

    Returns:
        List of AssetRendition instances that were touched.
    """
    if asset.asset_type != "image":
        return []

    # SVG: vectors are resolution-independent. Rasterizing to PNG/WebP/AVIF
    # at fixed widths just loses information. Leave the source file alone
    # and let the enhancer emit a bare <img> pointing at the SVG.
    if (asset.file_extension or "").lower() == "svg":
        return []

    if widths is None:
        widths = getattr(
            settings, "ASSET_RENDITION_WIDTHS", [400, 800, 1200, 1600, 2400]
        )
    jpeg_quality = getattr(settings, "ASSET_RENDITION_JPEG_QUALITY", 85)

    touched = []

    try:
        file_obj = open_field_file(asset.file)
        with Image.open(file_obj) as img:
            img.load()
            is_animated = getattr(img, "is_animated", False) and img.n_frames > 1
            if is_animated:
                animated_touched = _generate_animated_renditions(
                    asset=asset,
                    img=img,
                    widths=widths,
                    jpeg_quality=jpeg_quality,
                )
                touched.extend(animated_touched)
                try:
                    file_obj.seek(0)
                except Exception:
                    pass
                return touched

            original_width, original_height = img.size
            original_pil_format = (img.format or "JPEG").upper()
            original_ext = original_pil_format.lower()
            if original_ext == "jpeg":
                original_ext = "jpg"

            modern_formats = _supported_modern_formats()
            if formats is None:
                # Default emitted set: AVIF + WebP + source.
                target_formats = [
                    *((tag, pil, ext) for tag, pil, ext, _mime in modern_formats),
                    (_SOURCE_FORMAT_TAG, original_pil_format, original_ext),
                ]
            else:
                target_formats = []
                for fmt in formats:
                    if fmt == _SOURCE_FORMAT_TAG:
                        target_formats.append(
                            (_SOURCE_FORMAT_TAG, original_pil_format, original_ext)
                        )
                    else:
                        match = next((m for m in _MODERN_FORMATS if m[0] == fmt), None)
                        if match:
                            target_formats.append((match[0], match[1], match[2]))

            # Standard srcset widths.
            for width in widths:
                if width >= original_width:
                    continue
                height = int((width / original_width) * original_height)

                resized = img.copy()
                resized.thumbnail((width, height), Image.Resampling.LANCZOS)

                for fmt_tag, pil_format, ext in target_formats:
                    r = _encode_and_save_rendition(
                        asset=asset,
                        source_img=resized,
                        width=width,
                        height=height,
                        fmt_tag=fmt_tag,
                        pil_format=pil_format,
                        ext=ext,
                        preset="",
                        jpeg_quality=jpeg_quality,
                    )
                    if r is not None:
                        touched.append(r)

            # Social-share crops (focal-point aware).
            focal_x = asset.focal_point_x if asset.focal_point_x is not None else 0.5
            focal_y = asset.focal_point_y if asset.focal_point_y is not None else 0.5

            for preset, crop_w, crop_h in _SOCIAL_CROPS:
                if crop_w > original_width or crop_h > original_height:
                    continue
                box = _compute_focal_crop_box(
                    original_width,
                    original_height,
                    crop_w,
                    crop_h,
                    focal_x,
                    focal_y,
                )
                cropped = img.crop(box).resize(
                    (crop_w, crop_h), Image.Resampling.LANCZOS
                )
                for fmt_tag, pil_format, ext in target_formats:
                    r = _encode_and_save_rendition(
                        asset=asset,
                        source_img=cropped,
                        width=crop_w,
                        height=crop_h,
                        fmt_tag=fmt_tag,
                        pil_format=pil_format,
                        ext=ext,
                        preset=preset,
                        jpeg_quality=jpeg_quality,
                    )
                    if r is not None:
                        touched.append(r)

        try:
            file_obj.seek(0)
        except Exception:
            pass

    except Exception as exc:
        logger.exception("Rendition pipeline aborted for asset %s: %s", asset.key, exc)

    return touched


def _encode_and_save_rendition(
    *,
    asset,
    source_img,
    width,
    height,
    fmt_tag,
    pil_format,
    ext,
    preset,
    jpeg_quality,
):
    """Encode ``source_img`` and attach it to the AssetRendition row.

    Returns the rendition on success, or None if this variant was already
    complete (idempotent re-runs). Failures are logged + surfaced on the
    rendition's ``error_message``.
    """
    from .models import AssetRendition

    rendition, _ = AssetRendition.objects.get_or_create(
        asset=asset,
        width=width,
        format=fmt_tag,
        quality=AssetRendition.Quality.HIGH,
        defaults={
            "height": height,
            "preset": preset,
            "status": AssetRendition.Status.PENDING,
            # file_size is NOT NULL at the schema level. We don't know the
            # real size until encoding finishes below, so seed a 0 that gets
            # overwritten before the final save.
            "file_size": 0,
        },
    )
    if (
        rendition.file
        and rendition.status == AssetRendition.Status.COMPLETED
        and rendition.preset == preset
    ):
        return None

    rendition.status = AssetRendition.Status.PROCESSING
    rendition.error_message = ""
    rendition.preset = preset
    rendition.save(update_fields=["status", "error_message", "preset"])

    try:
        content = _save_to_bytes(
            source_img.copy(), pil_format, jpeg_quality=jpeg_quality
        )
    except Exception as render_exc:
        rendition.status = AssetRendition.Status.FAILED
        rendition.error_message = str(render_exc)[:500]
        rendition.save(update_fields=["status", "error_message"])
        logger.warning(
            "Rendition %sw %s (%s) failed for asset %s: %s",
            width,
            fmt_tag,
            preset or "base",
            asset.key,
            render_exc,
        )
        return None

    preset_tag = f"-{preset}" if preset else ""
    filename = f"{asset.key}{preset_tag}-{width}w.{ext}"
    rendition.file.save(filename, ContentFile(content), save=False)
    rendition.height = height
    rendition.file_size = len(content)
    rendition.is_webp = fmt_tag == "webp"
    rendition.status = AssetRendition.Status.COMPLETED
    rendition.save()
    return rendition


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
            result["errors"].append("Could not guess MIME type from file extension.")
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
                logger.exception(
                    "Image dimension extraction failed for %s", instance.key
                )
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

    video_streams = [
        s for s in data.get("streams", []) if s.get("codec_type") == "video"
    ]
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
    from django.conf import settings

    # Under ``manage.py test`` we skip the async task chain entirely: both
    # extract_metadata_async and generate_renditions_async would otherwise
    # run eagerly and block in Celery internals. Tests that need those
    # behaviors call the underlying functions (``extract_all_metadata``,
    # ``generate_asset_renditions``) directly.
    if getattr(settings, "TESTING", False):
        return

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
