"""
Tests for the asset image pipeline: rendition generation + the image
enhancer postprocessor that emits <picture>/srcset/sizes.

Also covers the video pipeline: poster extraction, transcoding, and the
video enhancer's multi-<source> + preload/autoplay/poster emission.
"""

import datetime
import os
import subprocess
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from engine.markdown.postprocessors.asset_image_enhancer import (
    _LCP_MIN_INTRINSIC_WIDTH,
    _collect_figure_classes,
    _sizes_for_figure,
    enhance_image_assets,
)
from engine.markdown.postprocessors.asset_video_enhancer import (
    enhance_video_assets,
)
from engine.models import Asset, AssetMetadata, AssetRendition
from engine.utils import generate_asset_renditions


def _build_image_bytes(width: int, height: int, fmt: str = "PNG") -> bytes:
    """Return raw bytes of a solid-red PIL image at the given size."""
    buf = BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, format=fmt)
    return buf.getvalue()


def _make_image_asset(
    key: str = "pipeline-test",
    *,
    width: int = 2000,
    height: int = 1000,
    fmt: str = "PNG",
    ext: str = "png",
) -> Asset:
    """Create a live Asset backed by a tiny solid-color source image.

    Status is "draft" (not "ready") so the post_save signal skips its
    synchronous rendition pass — tests that need renditions call
    ``generate_asset_renditions`` explicitly with a bounded widths list.
    Without this guard, AVIF encoding at 5 default widths makes the suite
    take minutes.
    """
    data = _build_image_bytes(width, height, fmt)
    uploaded = SimpleUploadedFile(f"{key}.{ext}", data, content_type=f"image/{ext}")
    return Asset.objects.create(
        title=key,
        key=key,
        asset_type="image",
        file=uploaded,
        status="draft",
        width=width,
        height=height,
    )


class SizesHelperTests(TestCase):
    """`_sizes_for_figure` is pure — test the branches directly."""

    def test_default_figure(self):
        self.assertEqual(
            _sizes_for_figure([], None),
            "(max-width: 649px) 100vw, 935px",
        )

    def test_width_full_spans_viewport(self):
        self.assertEqual(_sizes_for_figure(["width-full"], None), "100vw")

    def test_float_figure_uses_half_column(self):
        result = _sizes_for_figure(["float-right"], None)
        self.assertIn("50vw", result)
        self.assertIn("467px", result)

    def test_author_display_width_overrides(self):
        # Author pinned the image to 400px — browser should not fetch a 1600w.
        result = _sizes_for_figure(["float-right"], 400)
        self.assertIn("400px", result)
        self.assertNotIn("50vw", result)


class CollectFigureClassesTests(TestCase):
    """The early class-gathering step used to compute ``sizes``."""

    def test_inherits_from_parent_figure(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            '<figure class="float-right"><img class="inline" src="x"></figure>',
            "html.parser",
        )
        img = soup.find("img")
        classes = _collect_figure_classes(img)
        self.assertIn("float-right", classes)
        self.assertIn("inline", classes)

    def test_ignores_non_positioning_classes(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            '<img class="focusable some-other" src="x">',
            "html.parser",
        )
        classes = _collect_figure_classes(soup.find("img"))
        self.assertEqual(classes, [])


class RenditionGenerationTests(TestCase):
    """Exercise ``generate_asset_renditions`` end-to-end on tiny real images."""

    def test_still_image_generates_modern_and_source_formats(self):
        asset = _make_image_asset(key="rendition-still", width=2000, height=1000)

        touched = generate_asset_renditions(asset, widths=[400, 800])

        self.assertGreater(len(touched), 0)
        formats = {r.format for r in touched if r.preset == ""}
        self.assertIn("auto", formats)
        self.assertIn("webp", formats)
        widths = {r.width for r in touched if r.preset == ""}
        self.assertEqual(widths, {400, 800})

    def test_svg_is_bypassed(self):
        asset = Asset.objects.create(
            title="svg-bypass",
            key="svg-bypass",
            asset_type="image",
            file=SimpleUploadedFile(
                "logo.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                content_type="image/svg+xml",
            ),
            status="draft",
            width=100,
            height=100,
        )
        touched = generate_asset_renditions(asset, widths=[400, 800])
        self.assertEqual(touched, [])
        self.assertFalse(asset.renditions.exists())

    def test_skips_widths_at_or_above_original(self):
        asset = _make_image_asset(key="rendition-small", width=600, height=400)
        touched = generate_asset_renditions(asset, widths=[400, 800, 1200])
        widths = {r.width for r in touched if r.preset == ""}
        self.assertEqual(widths, {400})


class ImageEnhancerOutputTests(TestCase):
    """Render HTML through the enhancer and inspect the DOM it emits."""

    @classmethod
    def setUpTestData(cls):
        cls.asset = _make_image_asset(key="enhance-me", width=1800, height=1200)
        # Two modern-format renditions at different widths so a <picture>
        # will be built.
        AssetRendition.objects.create(
            asset=cls.asset,
            width=400,
            height=267,
            format="webp",
            quality=AssetRendition.Quality.HIGH,
            preset="",
            status=AssetRendition.Status.COMPLETED,
            file=SimpleUploadedFile("a-400.webp", b"fake", content_type="image/webp"),
            file_size=4,
        )
        AssetRendition.objects.create(
            asset=cls.asset,
            width=800,
            height=533,
            format="webp",
            quality=AssetRendition.Quality.HIGH,
            preset="",
            status=AssetRendition.Status.COMPLETED,
            file=SimpleUploadedFile("a-800.webp", b"fake", content_type="image/webp"),
            file_size=4,
        )
        AssetRendition.objects.create(
            asset=cls.asset,
            width=800,
            height=533,
            format="auto",
            quality=AssetRendition.Quality.HIGH,
            preset="",
            status=AssetRendition.Status.COMPLETED,
            file=SimpleUploadedFile("a-800.jpg", b"fake", content_type="image/jpeg"),
            file_size=4,
        )

    @staticmethod
    def _run(html: str) -> str:
        return enhance_image_assets(html, context={})

    def test_emits_picture_with_webp_source(self):
        html = (
            f'<p><img alt="x" src="/orig.jpg#asset-data:{self.asset.key}'
            f":image:1800:1200\"></p>"
        )
        out = self._run(html)
        self.assertIn("<picture>", out)
        self.assertIn('type="image/webp"', out)
        self.assertIn("400w", out)

    def test_default_sizes_without_positioning_class(self):
        html = (
            f'<p><img alt="x" src="/orig.jpg#asset-data:{self.asset.key}:image"></p>'
        )
        out = self._run(html)
        self.assertIn('sizes="(max-width: 649px) 100vw, 935px"', out)

    def test_float_right_changes_sizes(self):
        html = (
            f'<figure class="float-right">'
            f'<img alt="x" src="/orig.jpg#asset-data:{self.asset.key}:image">'
            f'</figure>'
        )
        out = self._run(html)
        self.assertIn("50vw", out)
        self.assertIn("467px", out)

    def test_fetchpriority_only_when_large(self):
        small = _make_image_asset(key="small-avatar", width=200, height=200)
        html = (
            f'<p><img alt="a" src="/a.jpg#asset-data:{small.key}:image"></p>'
            f'<p><img alt="b" src="/b.jpg#asset-data:{self.asset.key}:image"></p>'
        )
        out = self._run(html)

        # Avatar is tiny — it must not claim the LCP slot.
        # The large second image should get fetchpriority="high".
        self.assertEqual(out.count('fetchpriority="high"'), 1)
        # Check constant to make test self-explanatory when someone tweaks it.
        self.assertLess(200, _LCP_MIN_INTRINSIC_WIDTH)

    def test_svg_bypass_emits_no_picture(self):
        svg = Asset.objects.create(
            title="svg-enh",
            key="svg-enh",
            asset_type="image",
            file=SimpleUploadedFile(
                "logo.svg", b"<svg/>", content_type="image/svg+xml"
            ),
            status="draft",
            width=120,
            height=120,
        )
        html = (
            f'<p><img alt="logo" src="/logo.svg#asset-data:{svg.key}:image"></p>'
        )
        out = self._run(html)
        self.assertNotIn("<picture>", out)
        self.assertNotIn("srcset=", out)

    def test_lqip_data_url_applied_as_background(self):
        AssetMetadata.objects.create(
            asset=self.asset,
            average_color="#112233",
            lqip_data_url="data:image/webp;base64,UklGRg==",
        )
        # Reset the placeholder cache since setUpTestData created the asset
        # without metadata.
        if hasattr(self.asset, "_cached_placeholder"):
            delattr(self.asset, "_cached_placeholder")
        html = (
            f'<p><img alt="x" src="/orig.jpg#asset-data:{self.asset.key}:image"></p>'
        )
        out = self._run(html)
        self.assertIn("background-image: url(data:image/webp;base64,", out)
        self.assertIn("background-color: #112233", out)


# ---------------------------------------------------------------------------
# Video pipeline
# ---------------------------------------------------------------------------


def _make_video_asset(
    key: str = "video-pipeline-test",
    *,
    width: int = 1920,
    height: int = 1080,
    duration_s: int = 10,
    mime_type: str = "video/mp4",
    ext: str = "mp4",
) -> Asset:
    """Create a video Asset with pre-populated metadata. status="draft"
    keeps the post_save signal from trying to run ffprobe against the
    fake bytes.
    """
    uploaded = SimpleUploadedFile(
        f"{key}.{ext}", b"\x00\x00\x00\x00fake-video-bytes", content_type=mime_type
    )
    return Asset.objects.create(
        title=key,
        key=key,
        asset_type="video",
        file=uploaded,
        status="draft",
        width=width,
        height=height,
        duration=datetime.timedelta(seconds=duration_s),
        bitrate=5000,
        frame_rate="30.00",
        mime_type=mime_type,
    )


def _tiny_jpeg_bytes() -> bytes:
    """Return a valid JPEG PIL can open — used as a fake ffmpeg poster
    output so the PIL re-encode path in extract_poster succeeds.

    The image has multiple colours across a 128x72 canvas so the
    dominant-colour/LQIP extractor's ``quantize(colors=10)`` returns a
    full 30-entry palette; a solid-colour 64x36 image makes quantize emit
    a sub-10 palette that triggers an IndexError in the colour helper.
    """
    w, h = 128, 72
    img = Image.new("RGB", (w, h), color=(10, 20, 30))
    pixels = img.load()
    for x in range(w):
        for y in range(h):
            pixels[x, y] = (
                (x * 2) % 256,
                (y * 3) % 256,
                (x + y) % 256,
            )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _mock_ffmpeg(output_bytes_by_ext):
    """Return a ``subprocess.run`` side_effect that writes ``output_bytes``
    to the path following ``-y`` in argv (ffmpeg's output path convention
    used by video_pipeline). ``output_bytes_by_ext`` is a dict mapping the
    output extension → bytes to write.
    """

    def _side_effect(argv, *args, **kwargs):
        # Output file is always the positional after "-y".
        try:
            y_idx = argv.index("-y")
            out_path = argv[y_idx + 1]
        except (ValueError, IndexError):
            out_path = None

        if out_path:
            ext = os.path.splitext(out_path)[1].lstrip(".").lower()
            payload = output_bytes_by_ext.get(ext, output_bytes_by_ext.get("*", b"\x00"))
            with open(out_path, "wb") as fh:
                fh.write(payload)

        return subprocess.CompletedProcess(argv, 0, "", "")

    return _side_effect


def _mock_ffmpeg_failure(returncode: int = 1, stderr: str = "simulated ffmpeg failure"):
    def _side_effect(argv, *args, **kwargs):
        return subprocess.CompletedProcess(argv, returncode, "", stderr)

    return _side_effect


class VideoPosterExtractionTests(TestCase):
    """``extract_poster`` grabs a frame, re-encodes to WebP, and writes
    placeholder metadata."""

    def test_poster_rendition_created(self):
        asset = _make_video_asset(key="poster-basic")
        jpeg_bytes = _tiny_jpeg_bytes()

        with patch(
            "engine.video_pipeline._ffmpeg_bin", return_value="/usr/bin/ffmpeg"
        ), patch(
            "engine.video_pipeline.subprocess.run",
            side_effect=_mock_ffmpeg({"jpg": jpeg_bytes}),
        ):
            from engine.video_pipeline import extract_poster

            rendition = extract_poster(asset)

        self.assertIsNotNone(rendition)
        self.assertEqual(rendition.preset, "poster")
        self.assertEqual(rendition.format, "webp")
        self.assertEqual(rendition.status, AssetRendition.Status.COMPLETED)
        self.assertTrue(rendition.file)

        # JPEG fallback rendition also written.
        jpg_rendition = AssetRendition.objects.get(
            asset=asset, preset="poster", format="auto"
        )
        self.assertEqual(jpg_rendition.status, AssetRendition.Status.COMPLETED)

    def test_poster_populates_lqip_and_colors(self):
        asset = _make_video_asset(key="poster-placeholders")
        jpeg_bytes = _tiny_jpeg_bytes()

        with patch(
            "engine.video_pipeline._ffmpeg_bin", return_value="/usr/bin/ffmpeg"
        ), patch(
            "engine.video_pipeline.subprocess.run",
            side_effect=_mock_ffmpeg({"jpg": jpeg_bytes}),
        ):
            from engine.video_pipeline import extract_poster

            extract_poster(asset)

        meta = AssetMetadata.objects.get(asset=asset)
        self.assertTrue(meta.lqip_data_url)
        self.assertTrue(meta.lqip_data_url.startswith("data:image/"))
        self.assertRegex(meta.average_color, r"^#[0-9a-f]{6}$")

    def test_poster_failure_marks_rendition_failed(self):
        asset = _make_video_asset(key="poster-fail")

        with patch(
            "engine.video_pipeline._ffmpeg_bin", return_value="/usr/bin/ffmpeg"
        ), patch(
            "engine.video_pipeline.subprocess.run",
            side_effect=_mock_ffmpeg_failure(stderr="codec borked"),
        ):
            from engine.video_pipeline import extract_poster

            rendition = extract_poster(asset)

        self.assertIsNone(rendition)
        failed = AssetRendition.objects.filter(
            asset=asset, preset="poster", status=AssetRendition.Status.FAILED
        ).first()
        self.assertIsNotNone(failed)
        self.assertIn("borked", failed.error_message)

    def test_seek_time_clamped_for_short_video(self):
        asset = _make_video_asset(key="poster-short", duration_s=1)
        jpeg_bytes = _tiny_jpeg_bytes()
        captured_argv = []

        def _capture(argv, *args, **kwargs):
            captured_argv.append(list(argv))
            return _mock_ffmpeg({"jpg": jpeg_bytes})(argv, *args, **kwargs)

        with patch(
            "engine.video_pipeline._ffmpeg_bin", return_value="/usr/bin/ffmpeg"
        ), patch("engine.video_pipeline.subprocess.run", side_effect=_capture):
            from engine.video_pipeline import extract_poster

            extract_poster(asset)

        # The ffmpeg argv must include -ss immediately followed by "0".
        argv = captured_argv[0]
        ss_idx = argv.index("-ss")
        self.assertEqual(argv[ss_idx + 1], "0")


class VideoRenditionGenerationTests(TestCase):
    """``generate_video_renditions`` plans MP4+WebM at each feasible
    resolution and writes them as AssetRendition rows."""

    def test_generates_mp4_and_webm_at_each_resolution(self):
        asset = _make_video_asset(key="transcode-1080", width=1920, height=1080)

        with patch(
            "engine.video_pipeline._ffmpeg_bin", return_value="/usr/bin/ffmpeg"
        ), patch(
            "engine.video_pipeline._probe_output_bitrate", return_value=2500
        ), patch(
            "engine.video_pipeline.subprocess.run",
            side_effect=_mock_ffmpeg(
                {"mp4": b"fake-mp4-bytes", "webm": b"fake-webm-bytes"}
            ),
        ):
            from engine.video_pipeline import generate_video_renditions

            touched = generate_video_renditions(asset, resolutions=(720, 1080))

        self.assertEqual(len(touched), 4)
        presets = {r.preset for r in touched}
        self.assertEqual(presets, {"video-720p", "video-1080p"})
        formats = {(r.preset, r.format) for r in touched}
        self.assertIn(("video-720p", "mp4"), formats)
        self.assertIn(("video-720p", "webm"), formats)
        self.assertIn(("video-1080p", "mp4"), formats)
        self.assertIn(("video-1080p", "webm"), formats)
        for r in touched:
            self.assertEqual(r.status, AssetRendition.Status.COMPLETED)
            self.assertEqual(r.bitrate, 2500)

    def test_skips_resolution_larger_than_source(self):
        # 720p source → 1080p must be skipped (never upscale).
        asset = _make_video_asset(key="transcode-720", width=1280, height=720)

        with patch(
            "engine.video_pipeline._ffmpeg_bin", return_value="/usr/bin/ffmpeg"
        ), patch(
            "engine.video_pipeline._probe_output_bitrate", return_value=1500
        ), patch(
            "engine.video_pipeline.subprocess.run",
            side_effect=_mock_ffmpeg(
                {"mp4": b"fake-mp4", "webm": b"fake-webm"}
            ),
        ):
            from engine.video_pipeline import generate_video_renditions

            touched = generate_video_renditions(asset, resolutions=(720, 1080))

        presets = {r.preset for r in touched}
        self.assertEqual(presets, {"video-720p"})

    def test_failure_sets_error_message_and_continues(self):
        asset = _make_video_asset(key="transcode-fail", width=1280, height=720)

        # webm call fails; mp4 call succeeds.
        def _side_effect(argv, *args, **kwargs):
            out_ext = None
            try:
                out_path = argv[argv.index("-y") + 1]
                out_ext = os.path.splitext(out_path)[1].lstrip(".").lower()
            except (ValueError, IndexError):
                pass
            if out_ext == "webm":
                return subprocess.CompletedProcess(argv, 1, "", "vp9 broke")
            # Happy path for mp4.
            if out_ext == "mp4":
                with open(argv[argv.index("-y") + 1], "wb") as fh:
                    fh.write(b"ok")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with patch(
            "engine.video_pipeline._ffmpeg_bin", return_value="/usr/bin/ffmpeg"
        ), patch(
            "engine.video_pipeline._probe_output_bitrate", return_value=None
        ), patch(
            "engine.video_pipeline.subprocess.run", side_effect=_side_effect
        ):
            from engine.video_pipeline import generate_video_renditions

            touched = generate_video_renditions(asset, resolutions=(720,))

        mp4 = next(r for r in touched if r.format == "mp4")
        webm = next(r for r in touched if r.format == "webm")
        self.assertEqual(mp4.status, AssetRendition.Status.COMPLETED)
        self.assertEqual(webm.status, AssetRendition.Status.FAILED)
        self.assertIn("vp9", webm.error_message)

    def test_rerun_is_idempotent(self):
        asset = _make_video_asset(key="transcode-repeat", width=1280, height=720)

        with patch(
            "engine.video_pipeline._ffmpeg_bin", return_value="/usr/bin/ffmpeg"
        ), patch(
            "engine.video_pipeline._probe_output_bitrate", return_value=1500
        ), patch(
            "engine.video_pipeline.subprocess.run",
            side_effect=_mock_ffmpeg({"mp4": b"x", "webm": b"y"}),
        ):
            from engine.video_pipeline import generate_video_renditions

            generate_video_renditions(asset, resolutions=(720,))
            generate_video_renditions(asset, resolutions=(720,))

        # Still exactly two rows.
        self.assertEqual(
            AssetRendition.objects.filter(asset=asset, preset="video-720p").count(),
            2,
        )


class VideoEnhancerOutputTests(TestCase):
    """Render HTML through the video enhancer and inspect the emitted DOM."""

    @classmethod
    def setUpTestData(cls):
        cls.bare_asset = _make_video_asset(
            key="enhance-bare", width=1280, height=720
        )
        cls.rich_asset = _make_video_asset(
            key="enhance-rich", width=1920, height=1080
        )
        # Two video renditions + a poster for the "rich" asset.
        AssetRendition.objects.create(
            asset=cls.rich_asset,
            width=1920,
            height=1080,
            format="mp4",
            codec="h264",
            quality=AssetRendition.Quality.HIGH,
            preset="video-1080p",
            status=AssetRendition.Status.COMPLETED,
            file=SimpleUploadedFile(
                "rich-1080p.mp4", b"fake", content_type="video/mp4"
            ),
            file_size=4,
        )
        AssetRendition.objects.create(
            asset=cls.rich_asset,
            width=1920,
            height=1080,
            format="webm",
            codec="vp9",
            quality=AssetRendition.Quality.HIGH,
            preset="video-1080p",
            status=AssetRendition.Status.COMPLETED,
            file=SimpleUploadedFile(
                "rich-1080p.webm", b"fake", content_type="video/webm"
            ),
            file_size=4,
        )
        AssetRendition.objects.create(
            asset=cls.rich_asset,
            width=1280,
            height=720,
            format="webp",
            quality=AssetRendition.Quality.HIGH,
            preset="poster",
            status=AssetRendition.Status.COMPLETED,
            file=SimpleUploadedFile(
                "rich-poster.webp", b"fake", content_type="image/webp"
            ),
            file_size=4,
            is_webp=True,
        )

    def setUp(self):
        # The enhancer caches placeholder lookups on the asset instance;
        # clear between tests.
        for a in (self.bare_asset, self.rich_asset):
            for attr in ("_cached_video_placeholder", "_cached_placeholder"):
                if hasattr(a, attr):
                    delattr(a, attr)

    @staticmethod
    def _run(html: str) -> str:
        return enhance_video_assets(html, context={})

    def test_emits_webm_and_mp4_sources_when_renditions_exist(self):
        html = (
            f'<p><video src="/orig.mp4#asset-data:{self.rich_asset.key}:video">'
            f"</video></p>"
        )
        out = self._run(html)
        webm_idx = out.find('type="video/webm"')
        mp4_idx = out.find('type="video/mp4"')
        self.assertGreater(webm_idx, -1)
        self.assertGreater(mp4_idx, -1)
        self.assertLess(webm_idx, mp4_idx, "WebM source must precede MP4")

    def test_single_source_when_no_renditions(self):
        html = (
            f'<p><video src="/orig.mp4#asset-data:{self.bare_asset.key}:video">'
            f"</video></p>"
        )
        out = self._run(html)
        # Only the original source — no rendition URLs.
        self.assertEqual(out.count("<source"), 1)
        self.assertIn("/orig.mp4", out)

    def test_autoplay_implies_muted_and_playsinline(self):
        html = (
            f'<p><video src="/o.mp4#asset-data:{self.bare_asset.key}:video'
            f':autoplay=true"></video></p>'
        )
        out = self._run(html)
        self.assertIn("autoplay", out)
        self.assertIn("muted", out)
        self.assertIn("playsinline", out)

    def test_preload_none_when_poster_rendition_exists(self):
        html = (
            f'<p><video src="/o.mp4#asset-data:{self.rich_asset.key}:video">'
            f"</video></p>"
        )
        out = self._run(html)
        self.assertIn('preload="none"', out)

    def test_preload_metadata_when_no_poster(self):
        html = (
            f'<p><video src="/o.mp4#asset-data:{self.bare_asset.key}:video">'
            f"</video></p>"
        )
        out = self._run(html)
        self.assertIn('preload="metadata"', out)

    def test_preload_auto_when_autoplay(self):
        html = (
            f'<p><video src="/o.mp4#asset-data:{self.bare_asset.key}:video'
            f':autoplay=true"></video></p>'
        )
        out = self._run(html)
        self.assertIn('preload="auto"', out)

    def test_poster_rendition_url_used(self):
        html = (
            f'<p><video src="/o.mp4#asset-data:{self.rich_asset.key}:video">'
            f"</video></p>"
        )
        out = self._run(html)
        # The poster rendition's filename appears in the URL — not the
        # original file URL.
        self.assertIn("rich-poster", out)
        self.assertIn("poster=", out)

    def test_background_color_from_metadata(self):
        AssetMetadata.objects.create(
            asset=self.bare_asset,
            average_color="#445566",
            lqip_data_url="data:image/webp;base64,UklGRg==",
        )
        # Bust the cache seeded by prior tests in setUpTestData.
        if hasattr(self.bare_asset, "_cached_video_placeholder"):
            delattr(self.bare_asset, "_cached_video_placeholder")
        html = (
            f'<p><video src="/o.mp4#asset-data:{self.bare_asset.key}:video">'
            f"</video></p>"
        )
        out = self._run(html)
        self.assertIn("background-color: #445566", out)
        self.assertIn("background-image: url(data:image/webp;base64,", out)

    def test_original_not_duplicated_when_mp4_rendition_present(self):
        html = (
            f'<p><video src="/orig.mp4#asset-data:{self.rich_asset.key}:video">'
            f"</video></p>"
        )
        out = self._run(html)
        # Original was MP4 and we already have an MP4 rendition — don't
        # emit a third redundant MP4 <source>.
        self.assertEqual(out.count('type="video/mp4"'), 1)


class FinalizeUploadQueuesVideoProcessingTests(TestCase):
    """When ``finalize_presigned_upload`` sees a video, both the poster
    and the rendition Celery tasks must be queued."""

    def test_video_upload_queues_poster_and_renditions(self):
        from engine import tasks

        asset = _make_video_asset(key="finalize-video")
        # Switch to 'processing' to satisfy the task's state check.
        asset.status = "processing"
        asset.save(update_fields=["status"])

        with patch(
            "engine.api.presigned.verify_object_exists",
            return_value={"exists": True, "size": 1024},
        ), patch.object(
            tasks.extract_video_poster_async, "delay"
        ) as poster_delay, patch.object(
            tasks.generate_video_renditions_async, "delay"
        ) as rendition_delay, patch.object(
            tasks, "_extract_video_metadata"
        ), patch.object(
            tasks, "_calculate_file_hash"
        ), patch(
            "engine.metadata_extractor.extract_all_metadata", return_value=None
        ):
            tasks.finalize_presigned_upload(asset.pk)

        poster_delay.assert_called_once_with(asset.pk)
        rendition_delay.assert_called_once_with(asset.pk)
