"""
Video-side of the asset pipeline: poster-frame extraction, LQIP / dominant
colour derivation from the poster, and multi-codec transcoding to
H.264/AAC MP4 + VP9/Opus WebM at 720p / 1080p.

All ffmpeg work is isolated here so the Celery wrappers in ``engine.tasks``
stay thin. Pattern-for-pattern mirror of ``engine.utils`` (image encoding)
and ``engine.metadata_extractor`` (metadata extraction).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image

from .storage_utils import ensure_local_file

logger = logging.getLogger(__name__)


# MP4 + WebM are the only two containers we emit. AV1 is a deferred Tier-4
# item — once libaom/libsvtav1 is on the deploy image we can slot it in as
# another entry here without touching the enhancer's source-picking logic.
@dataclass(frozen=True)
class VideoCodec:
    format_tag: str   # AssetRendition.format value
    codec_tag: str    # AssetRendition.codec value
    ext: str          # file extension
    ffmpeg_args: tuple[str, ...]


_H264_MP4 = VideoCodec(
    format_tag="mp4",
    codec_tag="h264",
    ext="mp4",
    ffmpeg_args=(
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
    ),
)

_VP9_WEBM = VideoCodec(
    format_tag="webm",
    codec_tag="vp9",
    ext="webm",
    ffmpeg_args=(
        "-c:v", "libvpx-vp9",
        "-crf", "31",
        "-b:v", "0",
        "-row-mt", "1",
        "-c:a", "libopus",
        "-b:a", "96k",
    ),
)


_POSTER_WIDTH_CAP = 1280   # px — matches the 720p rendition width so the
                            # poster never outweighs the actual stream.
_POSTER_QUALITY_VFLAG = "3"  # ffmpeg -q:v for the intermediate JPEG grab
_SUBPROCESS_TIMEOUT_METADATA = 30    # seconds (ffprobe on an already-local file)
_SUBPROCESS_TIMEOUT_POSTER = 60      # seconds (single-frame grab)
_SUBPROCESS_TIMEOUT_TRANSCODE = 1800  # seconds (30 min — 1080p VP9 is slow)


def _ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg")


def _ffprobe_bin() -> str | None:
    return shutil.which("ffprobe")


def _poster_seek_time(asset) -> str:
    """Return the ``-ss`` argument: prefer 2 s in, fall back to 0 for clips
    shorter than that so we don't seek past the end.
    """
    if asset.duration and asset.duration.total_seconds() >= 2.0:
        return "00:00:02"
    return "0"


def _probe_output_bitrate(path: str) -> int | None:
    """Run ffprobe on a transcoded file and return its kbps, or None."""
    ffprobe = _ffprobe_bin()
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_METADATA,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        import json

        data = json.loads(proc.stdout or "{}")
        bit_rate = data.get("format", {}).get("bit_rate")
        if bit_rate:
            return int(bit_rate) // 1000
    except Exception:
        pass
    return None


def extract_poster(asset) -> "AssetRendition | None":
    """Grab a single frame from the video and store it as poster renditions.

    Emits two rows on the same (width, preset) — one WebP (modern) and one
    JPEG (legacy fallback). The enhancer prefers WebP but falls back to
    JPEG if the client or storage prevents serving it.

    Returns the WebP poster rendition on success, or None on any failure.
    """
    from .models import AssetRendition

    if asset.asset_type != "video":
        return None
    if not asset.file:
        return None

    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        logger.warning(
            "ffmpeg not on PATH — cannot extract poster for %s", asset.key
        )
        return None

    # Resolve poster dimensions from the known video dimensions; ffmpeg
    # takes -2 for "auto preserving aspect, even number".
    source_w = asset.width or _POSTER_WIDTH_CAP
    source_h = asset.height or 0
    target_w = min(_POSTER_WIDTH_CAP, source_w)
    if source_w and source_h:
        target_h = int(round(target_w * source_h / source_w))
        if target_h % 2:  # even for encoders' sake
            target_h -= 1
    else:
        target_h = None

    tmp_dir = tempfile.mkdtemp(prefix="poster-")
    try:
        jpg_path = os.path.join(tmp_dir, "poster.jpg")

        try:
            with ensure_local_file(asset.file) as local_path:
                proc = subprocess.run(
                    [
                        ffmpeg,
                        "-ss", _poster_seek_time(asset),
                        "-i", local_path,
                        "-frames:v", "1",
                        "-vf", f"scale='min({_POSTER_WIDTH_CAP},iw)':-2",
                        "-q:v", _POSTER_QUALITY_VFLAG,
                        "-y",
                        jpg_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=_SUBPROCESS_TIMEOUT_POSTER,
                )
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg poster timed out for %s", asset.key)
            return None
        except Exception as exc:
            logger.warning("ffmpeg poster failed for %s: %s", asset.key, exc)
            return None

        if proc.returncode != 0 or not os.path.exists(jpg_path):
            stderr_tail = (proc.stderr or "").strip().splitlines()[-1:] or ["exit %d" % proc.returncode]
            logger.warning(
                "ffmpeg poster failed for %s: %s", asset.key, stderr_tail[0]
            )
            _record_poster_failure(asset, stderr_tail[0])
            return None

        with open(jpg_path, "rb") as fh:
            jpg_bytes = fh.read()

        # Re-encode to WebP via PIL for the modern variant.
        try:
            with Image.open(BytesIO(jpg_bytes)) as img:
                img.load()
                poster_w, poster_h = img.size
                webp_buf = BytesIO()
                img.save(webp_buf, format="WEBP", quality=80, method=6)
                webp_bytes = webp_buf.getvalue()
        except Exception as exc:
            logger.warning("PIL poster WebP encode failed for %s: %s", asset.key, exc)
            return None

        webp_rendition = _store_poster_rendition(
            asset=asset,
            width=poster_w,
            height=poster_h,
            format_tag="webp",
            ext="webp",
            content=webp_bytes,
        )
        _store_poster_rendition(
            asset=asset,
            width=poster_w,
            height=poster_h,
            format_tag="auto",
            ext="jpg",
            content=jpg_bytes,
        )

        # Populate AssetMetadata (LQIP + dominant colour) from the same
        # poster bytes so later requests for the video get the
        # background-fill-while-loading treatment.
        try:
            populate_poster_placeholders(asset, jpg_bytes)
        except Exception as exc:
            logger.warning(
                "Poster placeholder extraction failed for %s: %s", asset.key, exc
            )

        return webp_rendition
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _record_poster_failure(asset, message: str) -> None:
    """Persist a FAILED poster rendition so the admin can see why."""
    from .models import AssetRendition

    rendition, _ = AssetRendition.objects.get_or_create(
        asset=asset,
        width=asset.width or _POSTER_WIDTH_CAP,
        format="webp",
        quality=AssetRendition.Quality.HIGH,
        preset="poster",
        defaults={"file_size": 0},
    )
    rendition.status = AssetRendition.Status.FAILED
    rendition.error_message = message[:500]
    rendition.save(update_fields=["status", "error_message"])


def _store_poster_rendition(
    *, asset, width, height, format_tag, ext, content,
):
    from .models import AssetRendition

    rendition, _ = AssetRendition.objects.get_or_create(
        asset=asset,
        width=width,
        format=format_tag,
        quality=AssetRendition.Quality.HIGH,
        preset="poster",
        defaults={"file_size": 0, "status": AssetRendition.Status.PENDING},
    )
    if (
        rendition.file
        and rendition.status == AssetRendition.Status.COMPLETED
    ):
        return rendition

    rendition.status = AssetRendition.Status.PROCESSING
    rendition.error_message = ""
    rendition.save(update_fields=["status", "error_message"])

    filename = f"{asset.key}-poster-{width}w.{ext}"
    rendition.file.save(filename, ContentFile(content), save=False)
    rendition.height = height
    rendition.file_size = len(content)
    rendition.is_webp = (format_tag == "webp")
    rendition.status = AssetRendition.Status.COMPLETED
    rendition.save()
    return rendition


def populate_poster_placeholders(asset, poster_bytes: bytes) -> None:
    """Feed the poster bytes through the image pipeline's LQIP + colour
    extractors and write the results onto the asset's ``AssetMetadata``.

    Reuses the same helpers that build placeholders for ``<img>`` so the
    ``<video>`` background-fill looks identical.
    """
    from .metadata_extractor import _extract_color_info, _extract_lqip
    from .models import AssetMetadata

    with Image.open(BytesIO(poster_bytes)) as img:
        img.load()
        lqip = _extract_lqip(img)
        colors = _extract_color_info(img)

    updates = {}
    if lqip:
        updates["lqip_data_url"] = lqip
    if colors.get("average_color"):
        updates["average_color"] = colors["average_color"]
    if colors.get("dominant_colors"):
        updates["dominant_colors"] = colors["dominant_colors"]
    if colors.get("color_palette"):
        updates["color_palette"] = colors["color_palette"]

    if not updates:
        return

    metadata, created = AssetMetadata.objects.get_or_create(asset=asset, defaults=updates)
    if not created:
        for field, value in updates.items():
            setattr(metadata, field, value)
        metadata.save(update_fields=list(updates.keys()))


def generate_video_renditions(
    asset, resolutions: tuple[int, ...] = (720, 1080)
) -> list:
    """Transcode ``asset`` into MP4 + WebM renditions at each requested
    resolution (by height, e.g. ``720`` → 720p).

    Returns the list of AssetRendition rows touched. Rows for resolutions
    that would upscale the source are skipped. Each codec failure is
    surfaced on ``error_message`` rather than raised so one bad variant
    doesn't abort the batch.
    """
    from .models import AssetRendition

    if asset.asset_type != "video":
        return []
    if not asset.file:
        return []

    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        logger.warning(
            "ffmpeg not on PATH — cannot transcode %s", asset.key
        )
        return []

    source_h = asset.height
    source_w = asset.width
    if not source_h or not source_w:
        logger.warning(
            "Asset %s missing width/height — cannot plan transcode targets",
            asset.key,
        )
        return []

    touched = []
    codecs = (_VP9_WEBM, _H264_MP4)

    with ensure_local_file(asset.file) as local_path:
        for target_h in resolutions:
            if target_h > source_h:
                # Never upscale.
                continue
            target_w = int(round(target_h * source_w / source_h))
            if target_w % 2:
                target_w -= 1
            preset = f"video-{target_h}p"

            for codec in codecs:
                rendition = _transcode_one(
                    asset=asset,
                    local_path=local_path,
                    codec=codec,
                    target_w=target_w,
                    target_h=target_h,
                    preset=preset,
                    ffmpeg=ffmpeg,
                )
                if rendition is not None:
                    touched.append(rendition)

    return touched


def _transcode_one(
    *, asset, local_path, codec: VideoCodec, target_w, target_h, preset, ffmpeg,
):
    from .models import AssetRendition

    rendition, _ = AssetRendition.objects.get_or_create(
        asset=asset,
        width=target_w,
        format=codec.format_tag,
        quality=AssetRendition.Quality.HIGH,
        preset=preset,
        defaults={
            "height": target_h,
            "codec": codec.codec_tag,
            "file_size": 0,
            "status": AssetRendition.Status.PENDING,
        },
    )
    if (
        rendition.file
        and rendition.status == AssetRendition.Status.COMPLETED
    ):
        return None

    rendition.status = AssetRendition.Status.PROCESSING
    rendition.error_message = ""
    rendition.codec = codec.codec_tag
    rendition.height = target_h
    rendition.save(update_fields=["status", "error_message", "codec", "height"])

    tmp_dir = tempfile.mkdtemp(prefix=f"rendition-{codec.format_tag}-")
    try:
        out_path = os.path.join(tmp_dir, f"out.{codec.ext}")
        cmd = [
            ffmpeg,
            "-i", local_path,
            "-vf", f"scale=-2:{target_h}",
            *codec.ffmpeg_args,
            "-y",
            out_path,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT_TRANSCODE,
            )
        except subprocess.TimeoutExpired:
            rendition.status = AssetRendition.Status.FAILED
            rendition.error_message = f"ffmpeg {codec.codec_tag} timed out"
            rendition.save(update_fields=["status", "error_message"])
            logger.warning(
                "ffmpeg %s %sp timed out for %s",
                codec.codec_tag, target_h, asset.key,
            )
            return rendition
        except Exception as exc:
            rendition.status = AssetRendition.Status.FAILED
            rendition.error_message = f"ffmpeg invocation failed: {exc}"[:500]
            rendition.save(update_fields=["status", "error_message"])
            logger.warning(
                "ffmpeg %s %sp invocation failed for %s: %s",
                codec.codec_tag, target_h, asset.key, exc,
            )
            return rendition

        if proc.returncode != 0 or not os.path.exists(out_path):
            stderr_tail = (proc.stderr or "").strip().splitlines()[-1:] or [f"exit {proc.returncode}"]
            rendition.status = AssetRendition.Status.FAILED
            rendition.error_message = stderr_tail[0][:500]
            rendition.save(update_fields=["status", "error_message"])
            logger.warning(
                "ffmpeg %s %sp failed for %s: %s",
                codec.codec_tag, target_h, asset.key, stderr_tail[0],
            )
            return rendition

        with open(out_path, "rb") as fh:
            content = fh.read()
        bitrate = _probe_output_bitrate(out_path)

        filename = f"{asset.key}-{preset}.{codec.ext}"
        rendition.file.save(filename, ContentFile(content), save=False)
        rendition.file_size = len(content)
        if bitrate:
            rendition.bitrate = bitrate
        rendition.status = AssetRendition.Status.COMPLETED
        rendition.save()
        return rendition
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
