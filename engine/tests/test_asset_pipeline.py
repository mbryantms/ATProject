"""
Tests for the asset image pipeline: rendition generation + the image
enhancer postprocessor that emits <picture>/srcset/sizes.
"""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from engine.markdown.postprocessors.asset_image_enhancer import (
    _LCP_MIN_INTRINSIC_WIDTH,
    _collect_figure_classes,
    _sizes_for_figure,
    enhance_image_assets,
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
