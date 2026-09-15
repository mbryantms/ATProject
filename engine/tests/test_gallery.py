"""
Tests for ``::: {.gallery}`` blocks: the image enhancer's gallery-aware
``sizes`` / stamping and the gallery postprocessor that builds the tiled
block, folds titles into tile captions and turns a trailing paragraph into
the gallery caption.
"""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from engine.markdown.postprocessors.asset_image_enhancer import (
    _sizes_for_figure,
    enhance_image_assets,
)
from engine.markdown.postprocessors.gallery_enhancer import (
    enhance_galleries,
    normalize_cols,
    normalize_rows,
)
from engine.markdown.renderer import render_markdown
from engine.models import Asset, AssetRendition


def _png(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color="blue").save(buf, format="PNG")
    return buf.getvalue()


def _asset(key: str, *, width: int, height: int, title: str = "", **extra) -> Asset:
    asset = Asset.objects.create(
        title=title,
        key=key,
        asset_type="image",
        file=SimpleUploadedFile(f"{key}.png", _png(width, height), "image/png"),
        status="draft",
        width=width,
        height=height,
        **extra,
    )
    # One fallback rendition so the enhancer emits srcset + sizes.
    AssetRendition.objects.create(
        asset=asset,
        width=400,
        height=round(400 * height / width),
        format="auto",
        quality=AssetRendition.Quality.HIGH,
        preset="",
        status=AssetRendition.Status.COMPLETED,
        file=SimpleUploadedFile(f"{key}-400.jpg", b"fake", content_type="image/jpeg"),
        file_size=4,
    )
    return asset


def _img(asset: Asset, alt: str = "x", caption: str | None = None) -> str:
    frag = f"#asset-data:{asset.key}:image:{asset.width}:{asset.height}"
    if caption is not None:
        frag += f":caption={caption}"
    return (
        f'<figure><img alt="{alt}" src="/{asset.key}.png{frag}">'
        f'<figcaption aria-hidden="true">{alt}</figcaption></figure>'
    )


def _run(html: str, context: dict | None = None) -> str:
    context = context if context is not None else {}
    return enhance_galleries(enhance_image_assets(html, context), context)


class SizesForGalleryTests(TestCase):
    def test_grid_divides_column_by_cols(self):
        sizes = _sizes_for_figure([], None, {"layout": "grid", "cols": 4})
        self.assertEqual(sizes, "(max-width: 649px) 50vw, 233px")

    def test_wall_and_strip_cap_at_400(self):
        for layout in ("wall", "strip"):
            sizes = _sizes_for_figure([], None, {"layout": layout, "cols": 3})
            self.assertEqual(sizes, "(max-width: 649px) 50vw, 400px")

    def test_display_width_still_wins(self):
        sizes = _sizes_for_figure([], 300, {"layout": "grid", "cols": 3})
        self.assertEqual(sizes, "(max-width: 649px) 100vw, 300px")

    def test_no_gallery_is_unchanged(self):
        self.assertEqual(_sizes_for_figure([], None), "(max-width: 649px) 100vw, 935px")


class NormalizersTests(TestCase):
    def test_rows(self):
        self.assertEqual(normalize_rows("tall"), "tall")
        self.assertEqual(normalize_rows(" Auto "), "auto")
        self.assertEqual(normalize_rows("260"), "260")
        self.assertIsNone(normalize_rows("huge"))
        self.assertIsNone(normalize_rows("10"))
        self.assertIsNone(normalize_rows(None))

    def test_cols(self):
        self.assertEqual(normalize_cols("4"), 4)
        self.assertIsNone(normalize_cols("1"))
        self.assertIsNone(normalize_cols("nine"))


class GalleryEnhancerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.wide = _asset("g-wide", width=1800, height=1200, title="Low tide")
        cls.tall = _asset(
            "g-tall",
            width=800,
            height=1200,
            title="",
            focal_point_x=0.25,
            focal_point_y=0.75,
        )

    def test_builds_items_container_and_marks_tiles(self):
        html = f'<div class="gallery grid" data-columns="4">{_img(self.wide)}{_img(self.tall)}</div>'
        out = _run(html)
        self.assertIn('class="gallery grid"', out)
        self.assertIn('data-count="2"', out)
        self.assertIn('data-row-height="auto"', out)
        self.assertIn('data-columns="4"', out)
        self.assertIn('data-captions="hover"', out)
        self.assertIn("--cols: 4", out)
        self.assertEqual(out.count('class="gallery-item"'), 2)
        self.assertIn('<div class="gallery-items">', out)
        # Tiles never carry the lone-figure spacing class.
        self.assertNotIn("block", out.split("gallery-items")[1].split("figure")[1])

    def test_tile_gets_aspect_ratio_focal_and_gallery_sizes(self):
        html = f'<div class="gallery grid" data-columns="4">{_img(self.tall)}</div>'
        out = _run(html)
        self.assertIn("--ar: 0.6667", out)
        self.assertIn("--focal: 25% 75%", out)
        self.assertIn('data-asset-key="g-tall"', out)
        self.assertIn('sizes="(max-width: 649px) 50vw, 233px"', out)
        self.assertNotIn('fetchpriority="high"', out)

    def test_title_becomes_bold_caption_line_and_alt_is_not_a_caption(self):
        html = f'<div class="gallery">{_img(self.wide, alt="Alt only")}</div>'
        out = _run(html)
        self.assertIn('<b class="figure-title">Low tide</b>', out)
        # Pandoc's alt-text figcaption is dropped inside a gallery.
        self.assertNotIn("Alt only</figcaption>", out)
        self.assertNotIn("Alt only</b>", out)

    def test_asset_caption_follows_title(self):
        html = f'<div class="gallery">{_img(self.wide, caption="Spring%20tide")}</div>'
        out = _run(html)
        self.assertIn('<b class="figure-title">Low tide</b>Spring tide', out)

    def test_untitled_uncaptioned_tile_has_no_caption(self):
        html = f'<div class="gallery">{_img(self.tall, alt="Ridge")}</div>'
        out = _run(html)
        self.assertNotIn("caption-wrapper", out)
        self.assertNotIn("<figcaption", out)

    def test_trailing_paragraph_becomes_gallery_caption(self):
        html = (
            f'<div class="gallery wall">{_img(self.wide)}'
            f"<p><strong>Point Reyes.</strong> One walk.</p></div>"
        )
        out = _run(html)
        self.assertIn(
            '<figcaption class="gallery-caption"><strong>Point Reyes.</strong> One walk.</figcaption>',
            out,
        )
        self.assertTrue(out.rstrip().endswith("</figcaption></div>"))

    def test_rows_override_and_validation(self):
        out = _run(
            f'<div class="gallery" data-row-height="tall">{_img(self.wide)}</div>'
        )
        self.assertIn('data-row-height="tall"', out)
        out = _run(
            f'<div class="gallery" data-row-height="huge">{_img(self.wide)}</div>'
        )
        self.assertIn('data-row-height="auto"', out)
        out = _run(
            f'<div class="gallery" data-row-height="260">{_img(self.wide)}</div>'
        )
        self.assertIn('data-row-height="260"', out)
        self.assertIn("--row-base: 260px", out)

    @override_settings(GALLERY_ROW_HEIGHT="short")
    def test_site_default_rows_from_settings(self):
        out = _run(f'<div class="gallery">{_img(self.wide)}</div>')
        self.assertIn('data-row-height="short"', out)

    def test_layout_defaults_to_wall_and_captions_validated(self):
        out = _run(
            f'<div class="gallery" data-captions="under">{_img(self.wide)}</div>'
        )
        self.assertIn('class="gallery wall"', out)
        self.assertIn('data-captions="under"', out)
        out = _run(
            f'<div class="gallery strip" data-captions="nope">{_img(self.wide)}</div>'
        )
        self.assertIn('class="gallery strip"', out)
        self.assertIn('data-captions="hover"', out)

    def test_lone_figure_is_untouched_by_gallery_rules(self):
        out = _run(_img(self.wide, alt="Alt text"))
        self.assertNotIn("gallery-item", out)
        self.assertIn("Alt text</figcaption>", out)  # alt fallback caption kept
        self.assertIn('data-asset-key="g-wide"', out)
        self.assertNotIn("data-title", out)
        self.assertIn('sizes="(max-width: 649px) 100vw, 935px"', out)


class GalleryMarkdownRoundTripTests(TestCase):
    """Pandoc's fenced-div output feeds the enhancer as expected."""

    def test_fenced_div_attributes_and_caption_survive_the_pipeline(self):
        md = (
            "::: {.gallery .grid columns=2 row-height=tall}\n\n"
            "![One](/one.jpg)\n\n"
            "![Two](/two.jpg)\n\n"
            "The set caption.\n\n"
            ":::\n"
        )
        out = render_markdown(md, context={})
        self.assertIn('class="gallery grid', out)
        self.assertIn('data-row-height="tall"', out)
        self.assertIn('data-columns="2"', out)
        self.assertIn('data-count="2"', out)
        self.assertEqual(out.count('class="gallery-item"'), 2)
        self.assertNotIn("gallery-item block", out)
        self.assertIn('class="gallery grid block"', out)
        self.assertIn(
            '<figcaption class="gallery-caption">The set caption.</figcaption>', out
        )
