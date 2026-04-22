"""
Postprocessor that enhances image assets with responsive features.

Adds:
- <picture> element with AVIF + WebP + source-format <source> entries so
  every browser gets the smallest format it understands
- srcset on each <source> / <img> using AssetRenditions
- Per-figure-class ``sizes`` so floated and width-full images fetch an
  appropriately sized variant
- loading="lazy" + decoding="async" on every image
- fetchpriority="high" on the first large image (LCP candidate), with
  optional ``{.lcp}`` author override
- LQIP (tiny base64 preview) + dominant/average-color placeholder to
  avoid the white flash while the image loads
- Figure wrappers with captions and positioning classes
- SVG bypass (leaves vector source untouched — no srcset / picture)
"""

import urllib.parse
from math import gcd

from bs4 import BeautifulSoup, NavigableString

from .utils import get_shared_soup, soup_to_html

_PICTURE_FORMATS = (
    ("avif", "image/avif"),
    ("webp", "image/webp"),
)

# Positioning classes that flow from the author's markdown onto the
# generated <figure>. Used for both CSS styling and ``sizes`` computation.
_POSITIONING_CLASSES = (
    "float-right",
    "float-left",
    "float-center",
    "width-full",
    "inline",
)

# An image needs to be this wide (intrinsic) to count as an LCP candidate.
# Small inline images (avatars, inline icons) that happen to appear first
# in the DOM shouldn't steal fetchpriority from the real hero below.
_LCP_MIN_INTRINSIC_WIDTH = 600


def _collect_figure_classes(img) -> list[str]:
    """Return positioning classes inherited from the img + parent figure.

    Mirrors what's computed later for the final <figure> class attribute,
    but runs early so ``sizes`` can use it.
    """
    classes: list[str] = []

    img_classes = img.get("class") or []
    if isinstance(img_classes, str):
        img_classes = img_classes.split()
    classes.extend(c for c in img_classes if c in _POSITIONING_CLASSES)

    parent = img.parent
    if parent is not None and parent.name == "figure":
        fig_classes = parent.get("class") or []
        if isinstance(fig_classes, str):
            fig_classes = fig_classes.split()
        classes.extend(c for c in fig_classes if c in _POSITIONING_CLASSES)

    return list(dict.fromkeys(classes))


def _sizes_for_figure(
    figure_classes: list[str], display_width: int | None
) -> str:
    """Compute a ``sizes`` attribute tuned to how wide the figure actually renders.

    Author-requested ``display_width`` always wins — if they pinned the image
    to 400px, the browser should never fetch a 1600w rendition.

    Otherwise:
    - ``.width-full`` figures break the 935px column and span the viewport.
    - ``.float-left`` / ``.float-right`` figures render at 50% of the column
      on wide viewports, full-width on mobile.
    - Everything else maxes out at the 935px body column.
    """
    if display_width:
        return f"(max-width: 649px) 100vw, {display_width}px"

    if "width-full" in figure_classes:
        return "100vw"

    if "float-left" in figure_classes or "float-right" in figure_classes:
        # 50vw above the 650px breakpoint until the column itself caps at
        # 935px, then locked at ~467px (half of 935 minus the gap).
        return "(max-width: 649px) 100vw, (max-width: 935px) 50vw, 467px"

    return "(max-width: 649px) 100vw, 935px"


def _lookup_placeholder(asset, AssetMetadata) -> tuple[str | None, str | None]:
    """Return (lqip_data_url, placeholder_color) for an asset, or (None, None).

    ``lqip_data_url`` renders a tiny blurred preview as a CSS background on
    the <img> so readers see the image's shape (not just a flat color) while
    the real pixels stream in. ``placeholder_color`` is the fallback when no
    LQIP has been generated yet.
    """
    cached = getattr(asset, "_cached_placeholder", None)
    if cached is not None:
        return cached

    try:
        metadata = AssetMetadata.objects.only(
            "dominant_colors", "average_color", "lqip_data_url"
        ).get(asset=asset)
    except AssetMetadata.DoesNotExist:
        asset._cached_placeholder = (None, None)
        return (None, None)

    color = None
    if metadata.dominant_colors and isinstance(metadata.dominant_colors, list):
        for candidate in metadata.dominant_colors:
            if isinstance(candidate, str) and candidate.startswith("#"):
                color = candidate
                break
    if not color and metadata.average_color:
        color = metadata.average_color

    lqip = getattr(metadata, "lqip_data_url", None) or None

    result = (lqip, color)
    asset._cached_placeholder = result
    return result


def enhance_image_assets(html: str, context: dict) -> str:
    """
    Enhance image assets with responsive attributes and lazy loading.

    Creates structure:
    <figure class="float-right float block" style="--bsm: 10;">
      <span class="figure-outer-wrapper">
        <span class="image-wrapper img focusable">
          <picture>
            <source type="image/avif" srcset="… 400w, … 800w, …" sizes="…">
            <source type="image/webp" srcset="… 400w, … 800w, …" sizes="…">
            <img … (source-format fallback with srcset)>
          </picture>
        </span>
        <span class="caption-wrapper">
          <figcaption>...</figcaption>
        </span>
      </span>
    </figure>
    """
    from engine.markdown.renderer import render_markdown
    from engine.models import Asset, AssetMetadata

    soup = get_shared_soup(html, context)
    lcp_emitted = False  # first eligible image gets fetchpriority="high"

    for img in list(soup.find_all("img")):
        src = img.get("src", "")

        if "#asset-data:" not in src:
            continue

        url_parts = src.split("#asset-data:")
        base_url = url_parts[0]
        metadata_str = url_parts[1]
        metadata_parts = metadata_str.split(":")

        if len(metadata_parts) < 2:
            continue

        asset_key = metadata_parts[0]
        asset_type = metadata_parts[1]

        if asset_type != "image":
            continue

        metadata = {}
        for part in metadata_parts[2:]:
            if "=" in part:
                k, v = part.split("=", 1)
                metadata[k] = urllib.parse.unquote(v)
            else:
                if "width" not in metadata and part.isdigit():
                    metadata["width"] = part
                elif "height" not in metadata and part.isdigit():
                    metadata["height"] = part

        try:
            asset = Asset.objects.get(key=asset_key)
        except Asset.DoesNotExist:
            continue

        img["src"] = base_url

        # SVG bypass: vectors scale natively, so a srcset + <picture> tree
        # only wastes bytes. Emit a plain <img> and let the browser handle
        # resizing. We still apply alt text, figure wrapping, and the
        # positioning classes below.
        is_svg = (asset.file_extension or "").lower() == "svg"

        intrinsic_width = (
            int(metadata.get("width")) if metadata.get("width") else asset.width
        )
        intrinsic_height = (
            int(metadata.get("height")) if metadata.get("height") else asset.height
        )

        display_width = (
            int(metadata.get("display_width"))
            if metadata.get("display_width")
            else None
        )
        display_height = (
            int(metadata.get("display_height"))
            if metadata.get("display_height")
            else None
        )

        if (
            display_width
            and not display_height
            and intrinsic_width
            and intrinsic_height
        ):
            display_height = int((display_width / intrinsic_width) * intrinsic_height)
        elif (
            display_height
            and not display_width
            and intrinsic_width
            and intrinsic_height
        ):
            display_width = int((display_height / intrinsic_height) * intrinsic_width)

        if intrinsic_width:
            img["width"] = intrinsic_width
        if intrinsic_height:
            img["height"] = intrinsic_height

        # Gather positioning classes early so the sizes attribute and the
        # final figure wrapper agree on geometry.
        figure_classes = _collect_figure_classes(img)
        sizes_attr = _sizes_for_figure(figure_classes, display_width)

        style_parts = []

        if intrinsic_width and intrinsic_height:
            divisor = gcd(intrinsic_width, intrinsic_height)
            aspect_w = intrinsic_width // divisor
            aspect_h = intrinsic_height // divisor
            img["data-aspect-ratio"] = f"{aspect_w} / {aspect_h}"
            style_parts.append(f"aspect-ratio: {aspect_w} / {aspect_h}")

            # See base.css figure img rule: --img-ar lets max-width track the
            # vertical headroom so aspect ratio survives short viewports.
            ar_decimal = intrinsic_width / intrinsic_height
            style_parts.append(f"--img-ar: {ar_decimal:.4f}")

        if display_width:
            style_parts.append(f"width: {display_width}px")
            # Don't emit inline ``height``: when both width and height are
            # explicit on an <img>, ``aspect-ratio`` is ignored, so on short
            # viewports ``max-width`` and ``max-height`` would clamp the two
            # dimensions independently and break the aspect ratio. With only
            # ``width`` set, the browser derives height from the inline
            # ``aspect-ratio`` and the clamps stay proportional.
        # No inline ``max-width`` in the intrinsic-size branch: it would
        # override the stylesheet's ``max-width: min(100%, (100dvh - 8rem) *
        # var(--img-ar))`` cap (inline beats class selectors), letting tall
        # images break out of the column on viewports where the viewport-
        # height branch of the min() would otherwise win. With ``width:
        # auto`` on ``figure img``, the browser already renders the image at
        # its intrinsic size by default; ``max-width`` only clamps down, so
        # the image never upscales past its natural pixels.

        if style_parts:
            existing_style = img.get("style", "").strip()
            if existing_style and not existing_style.endswith(";"):
                existing_style += ";"
            img["style"] = "; ".join(style_parts) + (
                "" if not existing_style else f"; {existing_style}"
            )

        # Responsive srcset / <picture> — skipped for SVG.
        picture_sources = []
        picture_element = None
        if not is_svg:
            base_renditions = asset.renditions.filter(
                preset="", status="completed"
            ).order_by("width")

            for fmt_tag, mime in _PICTURE_FORMATS:
                srcset = ", ".join(
                    f"{r.file.url} {r.width}w"
                    for r in base_renditions if r.format == fmt_tag
                )
                if srcset:
                    picture_sources.append((mime, srcset))

            fallback_srcset = ", ".join(
                f"{r.file.url} {r.width}w"
                for r in base_renditions if r.format == "auto"
            )
            if fallback_srcset:
                img["srcset"] = fallback_srcset
                img["sizes"] = sizes_attr

        if not img.get("loading"):
            img["loading"] = "lazy"
        if not img.get("decoding"):
            img["decoding"] = "async"

        # LCP candidate selection: the first in-body image that's either
        # (a) explicitly marked via {.lcp} or (b) big enough to plausibly be
        # the hero gets fetchpriority="high" + eager loading. Small leading
        # inline images pass through without burning the slot.
        img_classes_raw = img.get("class") or []
        if isinstance(img_classes_raw, str):
            img_classes_raw = img_classes_raw.split()

        is_author_lcp = "lcp" in img_classes_raw
        is_large_enough = (intrinsic_width or 0) >= _LCP_MIN_INTRINSIC_WIDTH

        if not lcp_emitted and (is_author_lcp or is_large_enough):
            img["fetchpriority"] = "high"
            img["loading"] = "eager"
            lcp_emitted = True

        lqip_data_url, placeholder_color = _lookup_placeholder(asset, AssetMetadata)
        bg_parts = []
        if lqip_data_url:
            bg_parts.append(f"background-image: url({lqip_data_url})")
            bg_parts.append("background-size: cover")
            bg_parts.append("background-position: center")
        if placeholder_color:
            bg_parts.append(f"background-color: {placeholder_color}")
        if bg_parts:
            existing_style = img.get("style", "").rstrip(" ;")
            prefix = f"{existing_style}; " if existing_style else ""
            img["style"] = f"{prefix}{'; '.join(bg_parts)}"

        if not img.get("alt"):
            img["alt"] = metadata.get("alt_text", asset.alt_text or "")

        # Build <picture> with <source> tags, but don't append img yet —
        # parent-tracking below reads img.parent to decide where the final
        # figure goes, and moving img into picture_element first makes
        # img.parent point into a detached tree (breaking extraction and
        # creating an insert-cycle if figure later gets put back into it).
        picture_element = None
        if picture_sources:
            picture_element = soup.new_tag("picture")
            for mime, srcset in picture_sources:
                source_tag = soup.new_tag("source")
                source_tag["type"] = mime
                source_tag["srcset"] = srcset
                source_tag["sizes"] = sizes_attr
                picture_element.append(source_tag)

        existing_img_classes = img_classes_raw  # already materialized above

        img_only_classes = [
            cls for cls in existing_img_classes if cls not in _POSITIONING_CLASSES
        ]
        img_classes = ["focusable", "gallery-image"] + img_only_classes

        if "invert" in img.get("alt", "").lower():
            if "invert" not in img_classes:
                img_classes.append("invert")

        img["class"] = img_classes

        existing_figure = None
        if img.parent is not None and img.parent.name == "figure":
            existing_figure = img.parent
            if existing_figure.get("class"):
                existing_classes = existing_figure.get("class")
                if isinstance(existing_classes, list):
                    figure_classes.extend(existing_classes)
                else:
                    figure_classes.extend(existing_classes.split())

        figure_classes = list(dict.fromkeys(figure_classes))

        if any(
            cls in figure_classes
            for cls in ["float-right", "float-left", "float-center"]
        ):
            if "float" not in figure_classes:
                figure_classes.append("float")

        if existing_figure:
            caption = metadata.get("caption", "")
            if not caption:
                existing_caption = existing_figure.find("figcaption")
                if existing_caption:
                    caption = "".join(str(c) for c in existing_caption.children)

            img.extract()

            figure_parent = existing_figure.parent
            figure_index = figure_parent.contents.index(existing_figure)

            existing_figure.decompose()

            figure = soup.new_tag("figure")
            all_classes = list(set(figure_classes + ["block"]))
            figure["class"] = all_classes

            outer_wrapper = soup.new_tag("span")
            outer_wrapper["class"] = ["figure-outer-wrapper"]

            image_wrapper = soup.new_tag("span")
            image_wrapper["class"] = ["image-wrapper", "img", "focusable"]
            if picture_element is not None:
                picture_element.append(img)
                image_wrapper.append(picture_element)
            else:
                image_wrapper.append(img)
            outer_wrapper.append(image_wrapper)

            if caption:
                caption_wrapper = soup.new_tag("span")
                caption_wrapper["class"] = ["caption-wrapper"]

                figcaption = soup.new_tag("figcaption")

                if metadata.get("caption"):
                    caption_html = render_markdown(caption, context=context)
                    caption_soup = BeautifulSoup(caption_html, "html.parser")

                    caption_content = caption_soup.find("p")
                    if caption_content:
                        for child in list(caption_content.children):
                            figcaption.append(child)
                    else:
                        for child in list(
                            caption_soup.body.children if caption_soup.body else []
                        ):
                            figcaption.append(child)
                else:
                    caption_parsed = BeautifulSoup(caption, "html.parser")
                    for child in list(caption_parsed.children):
                        figcaption.append(child)

                caption_wrapper.append(figcaption)
                outer_wrapper.append(caption_wrapper)

            figure.append(outer_wrapper)
            figure_parent.insert(figure_index, figure)

        else:
            caption = metadata.get("caption", "")

            img_parent = img.parent
            replace_parent = False
            img_parent_parent = None
            img_parent_index = None
            img_index = None

            if img_parent.name == "p":
                text_content = "".join(
                    [
                        str(c)
                        for c in img_parent.children
                        if isinstance(c, NavigableString)
                    ]
                ).strip()
                other_elements = [
                    c for c in img_parent.children if c.name and c.name != "img"
                ]

                if not text_content and not other_elements:
                    img_parent_parent = img_parent.parent
                    img_parent_index = img_parent_parent.contents.index(img_parent)
                    img_parent.extract()
                    img.extract()
                    replace_parent = True
                else:
                    img_index = img_parent.contents.index(img)
                    img.extract()
            else:
                img_index = img_parent.contents.index(img)
                img.extract()

            figure = soup.new_tag("figure")
            all_classes = list(set(figure_classes + ["block"]))
            figure["class"] = all_classes

            outer_wrapper = soup.new_tag("span")
            outer_wrapper["class"] = ["figure-outer-wrapper"]

            image_wrapper = soup.new_tag("span")
            image_wrapper["class"] = ["image-wrapper", "img", "focusable"]
            if picture_element is not None:
                picture_element.append(img)
                image_wrapper.append(picture_element)
            else:
                image_wrapper.append(img)
            outer_wrapper.append(image_wrapper)

            if caption:
                caption_wrapper = soup.new_tag("span")
                caption_wrapper["class"] = ["caption-wrapper"]

                figcaption = soup.new_tag("figcaption")

                caption_html = render_markdown(caption, context=context)
                caption_soup = BeautifulSoup(caption_html, "html.parser")

                caption_content = caption_soup.find("p")
                if caption_content:
                    for child in list(caption_content.children):
                        figcaption.append(child)
                else:
                    for child in list(
                        caption_soup.body.children if caption_soup.body else []
                    ):
                        figcaption.append(child)

                caption_wrapper.append(figcaption)
                outer_wrapper.append(caption_wrapper)

            figure.append(outer_wrapper)

            if replace_parent and img_parent_parent is not None:
                img_parent_parent.insert(img_parent_index, figure)
            else:
                img_parent.insert(img_index, figure)

    return soup_to_html(context, soup)


def asset_image_enhancer_default(html: str, context: dict) -> str:
    """Register this in POSTPROCESSORS."""
    return enhance_image_assets(html, context)
