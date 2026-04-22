"""
Postprocessor that enhances video assets with proper HTML5 video markup.

Creates structure matching image enhancer:
<figure class="float-right float block" style="--bsm: 10;">
  <span class="figure-outer-wrapper">
    <span class="image-wrapper video">
      <video controls preload="none" loop width="X" height="Y"
             data-aspect-ratio="X / Y" style="aspect-ratio: X / Y; width: XXXpx;"
             poster="...">
        <source src="..." type="video/mp4">
      </video>
    </span>
    <span class="caption-wrapper">
      <figcaption>...</figcaption>
    </span>
  </span>
</figure>
"""

import urllib.parse
from math import gcd

from bs4 import BeautifulSoup, NavigableString

from .utils import get_shared_soup, soup_to_html


_BOOLEAN_TRUE = ("true", "1", "yes", "on")


def _lookup_video_placeholder(asset, AssetMetadata) -> tuple[str | None, str | None]:
    """Return (lqip_data_url, placeholder_color) for a video's poster-derived
    metadata, or (None, None). Mirrors the image enhancer's helper so the
    same bytes are reused across repeat lookups within a render pass.
    """
    cached = getattr(asset, "_cached_video_placeholder", None)
    if cached is not None:
        return cached

    try:
        metadata = AssetMetadata.objects.only(
            "dominant_colors", "average_color", "lqip_data_url"
        ).get(asset=asset)
    except AssetMetadata.DoesNotExist:
        asset._cached_video_placeholder = (None, None)
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
    asset._cached_video_placeholder = result
    return result


def _poster_rendition_url(asset) -> str | None:
    """Prefer the WebP poster; fall back to the JPEG if only that is
    completed. Returns ``None`` if neither is ready yet.
    """
    poster_renditions = asset.renditions.filter(
        preset="poster", status="completed"
    )
    webp = next((r for r in poster_renditions if r.format == "webp"), None)
    if webp and webp.file:
        return webp.url
    other = next((r for r in poster_renditions if r.file), None)
    return other.url if other else None


def _select_video_sources(asset):
    """Pick the highest-resolution WebM and MP4 renditions for ``asset``.

    Returns a list of (url, mime_type) tuples ordered from modern-first
    (WebM/VP9) to legacy (MP4/H.264) to ``None``-return when renditions
    aren't ready yet. The caller still appends the original source as a
    final fallback when appropriate.
    """
    completed = list(
        asset.renditions.filter(
            preset__startswith="video-", status="completed"
        ).order_by("-height")
    )
    best_webm = next((r for r in completed if r.format == "webm" and r.file), None)
    best_mp4 = next((r for r in completed if r.format == "mp4" and r.file), None)

    sources = []
    if best_webm:
        sources.append((best_webm.url, "video/webm"))
    if best_mp4:
        sources.append((best_mp4.url, "video/mp4"))
    return sources, best_mp4 is not None


def enhance_video_assets(html: str, context: dict) -> str:
    """
    Enhance video assets with HTML5 video player and responsive features.

    Creates structure matching asset_image_enhancer for consistency.
    Uses shared soup caching for efficiency.
    """
    # Lazy import to avoid circular import
    from engine.markdown.renderer import render_markdown
    from engine.models import Asset, AssetMetadata

    soup = get_shared_soup(html, context)

    # Find all images AND videos with asset metadata
    # Pandoc may create <video> tags directly for .mov, .mp4, etc. extensions
    elements_to_process = []
    elements_to_process.extend(soup.find_all("img"))
    elements_to_process.extend(soup.find_all("video"))

    for element in list(elements_to_process):
        src = element.get("src", "")
        element_tag = element.name  # 'img' or 'video'

        # Check for asset metadata in URL fragment
        if "#asset-data:" not in src:
            continue

        # Parse metadata
        url_parts = src.split("#asset-data:")
        base_url = url_parts[0]
        metadata_str = url_parts[1]
        metadata_parts = metadata_str.split(":")

        if len(metadata_parts) < 2:
            continue

        asset_key = metadata_parts[0]
        asset_type = metadata_parts[1]

        if asset_type != "video":
            continue

        # Parse additional metadata
        metadata = {}
        for part in metadata_parts[2:]:
            if "=" in part:
                k, v = part.split("=", 1)
                metadata[k] = urllib.parse.unquote(v)
            else:
                # Positional: width, height (intrinsic dimensions from asset)
                if "width" not in metadata and part.isdigit():
                    metadata["width"] = part
                elif "height" not in metadata and part.isdigit():
                    metadata["height"] = part

        # Get asset
        try:
            asset = Asset.objects.get(key=asset_key)
        except Asset.DoesNotExist:
            continue

        # Determine intrinsic dimensions
        intrinsic_width = (
            int(metadata.get("width")) if metadata.get("width") else asset.width
        )
        intrinsic_height = (
            int(metadata.get("height")) if metadata.get("height") else asset.height
        )

        # Check for display size overrides
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

        # Calculate proportional dimensions if only one is specified
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

        # Existing classes on the source element feed into positioning
        # decisions (float-right / inline / etc.). Collect early so the
        # preload heuristic below can see them.
        early_classes_raw = element.get("class") or []
        if isinstance(early_classes_raw, str):
            early_classes_raw = early_classes_raw.split()
        has_inline_class = "inline" in early_classes_raw

        # Create video element
        video = soup.new_tag("video")
        video["controls"] = "controls"

        # Check for loop attribute from metadata
        if metadata.get("loop", "").lower() in _BOOLEAN_TRUE:
            video["loop"] = ""

        # autoplay implies muted+playsinline on mobile Safari — without the
        # full trio, iOS refuses to start playback.
        autoplay = metadata.get("autoplay", "").lower() in _BOOLEAN_TRUE
        if autoplay:
            video["autoplay"] = ""
            video["muted"] = ""
            video["playsinline"] = ""

        # Look up the poster BEFORE deciding on preload so the heuristic can
        # see whether we have something visible to show before the pixels land.
        poster_url = None
        if metadata.get("poster"):
            if metadata["poster"].startswith("@asset:"):
                poster_key = metadata["poster"].replace("@asset:", "")
                try:
                    poster_asset = Asset.objects.get(key=poster_key)
                    poster_url = poster_asset.file.url
                except Asset.DoesNotExist:
                    pass
            else:
                poster_url = metadata["poster"]
        if not poster_url:
            poster_url = _poster_rendition_url(asset)

        # preload heuristic. autoplay → auto (player needs bytes now).
        # inline or has-poster → none (poster covers the gap until the
        # user interacts). Otherwise metadata (current default; reveals
        # the first frame without pulling the full stream).
        if autoplay:
            video["preload"] = "auto"
        elif has_inline_class or poster_url:
            video["preload"] = "none"
        else:
            video["preload"] = "metadata"

        # Add intrinsic dimensions as attributes for aspect ratio calculation
        # Don't set height attribute - let CSS aspect-ratio handle it
        if intrinsic_width:
            video["width"] = intrinsic_width

        # Calculate aspect ratio and add style
        style_parts = []
        if intrinsic_width and intrinsic_height:
            # Simplify aspect ratio
            divisor = gcd(intrinsic_width, intrinsic_height)
            aspect_w = intrinsic_width // divisor
            aspect_h = intrinsic_height // divisor
            aspect_ratio = f"{aspect_w} / {aspect_h}"

            video["data-aspect-ratio"] = aspect_ratio
            style_parts.append(f"aspect-ratio: {aspect_w} / {aspect_h}")

            # --img-ar lets the shared ``figure img/video/svg`` CSS clamp
            # preserve aspect ratio under short viewports (see base.css).
            ar_decimal = intrinsic_width / intrinsic_height
            style_parts.append(f"--img-ar: {ar_decimal:.4f}")

        # Add display width to style (responsive)
        final_width = display_width if display_width else intrinsic_width
        if final_width:
            style_parts.append(f"max-width: {final_width}px")
            style_parts.append("width: 100%")

        # Optionally add display height
        if display_height and display_width:
            style_parts.append(f"height: {display_height}px")

        # Background-fill treatment — same visual as <img>. The LQIP is a
        # tiny blurred data-URL of the poster frame; placeholder_color is a
        # dominant/average colour. Both come from AssetMetadata populated
        # during poster extraction in video_pipeline.extract_poster.
        lqip_data_url, placeholder_color = _lookup_video_placeholder(
            asset, AssetMetadata
        )
        if lqip_data_url:
            style_parts.append(f"background-image: url({lqip_data_url})")
            style_parts.append("background-size: cover")
            style_parts.append("background-position: center")
        if placeholder_color:
            style_parts.append(f"background-color: {placeholder_color}")

        if style_parts:
            video["style"] = "; ".join(style_parts)

        if poster_url:
            video["data-video-poster"] = poster_url
            video["poster"] = poster_url

        # Multi-source emission ordered modern → legacy → original fallback.
        # The browser picks the first <source> whose codec it can decode.
        rendition_sources, has_mp4_rendition = _select_video_sources(asset)
        for src_url, mime_type in rendition_sources:
            source = soup.new_tag("source")
            source["src"] = src_url
            source["type"] = mime_type
            video.append(source)

        # Append the original file as a final fallback — but only if it's
        # not identical to a rendition we just emitted. When we already have
        # an MP4 rendition and the original is also MP4, the rendition is
        # strictly better (smaller, faststart'd), so skip the duplicate.
        source_mime = asset.mime_type or "video/mp4"
        if not (has_mp4_rendition and source_mime == "video/mp4"):
            fallback = soup.new_tag("source")
            fallback["src"] = base_url
            fallback["type"] = source_mime
            video.append(fallback)

        # Extract existing classes from element (Pandoc puts attributes on element)
        existing_element_classes = []
        if element.get("class"):
            if isinstance(element["class"], list):
                existing_element_classes = element["class"]
            else:
                existing_element_classes = element["class"].split()

        # Separate positioning classes from styling classes
        positioning_classes = [
            "float-right",
            "float-left",
            "float-center",
            "width-full",
            "inline",
        ]
        figure_classes = [
            cls for cls in existing_element_classes if cls in positioning_classes
        ]

        # Check if already wrapped in a markdown-generated figure
        existing_figure = None
        if element.parent.name == "figure":
            existing_figure = element.parent
            # Also extract classes from figure if present
            if existing_figure.get("class"):
                existing_classes = existing_figure.get("class")
                if isinstance(existing_classes, list):
                    figure_classes.extend(existing_classes)
                else:
                    figure_classes.extend(existing_classes.split())

        # Remove duplicates
        figure_classes = list(dict.fromkeys(figure_classes))

        # Add parent 'float' class if any float direction is specified
        if any(
            cls in figure_classes
            for cls in ["float-right", "float-left", "float-center"]
        ):
            if "float" not in figure_classes:
                figure_classes.append("float")

        # Always create enhanced figure structure
        if existing_figure:
            # Replace the existing markdown-generated figure with our enhanced structure
            # Get caption from metadata or existing figcaption
            caption = metadata.get("caption", "")
            if not caption:
                # Check for existing figcaption
                existing_caption = existing_figure.find("figcaption")
                if existing_caption:
                    caption = "".join(str(c) for c in existing_caption.children)

            # Extract the element
            element.extract()

            # Remember where the figure is
            figure_parent = existing_figure.parent
            figure_index = figure_parent.contents.index(existing_figure)

            # Remove the old figure
            existing_figure.decompose()

            # Create new enhanced figure
            figure = soup.new_tag("figure")
            # Combine extracted classes with 'block'
            all_classes = list(set(figure_classes + ["block"]))
            figure["class"] = all_classes

            # Create wrapper structure
            outer_wrapper = soup.new_tag("span")
            outer_wrapper["class"] = ["figure-outer-wrapper"]

            # Video wrapper (use "image-wrapper video" to match reference)
            video_wrapper = soup.new_tag("span")
            video_wrapper["class"] = ["image-wrapper", "video"]
            video_wrapper.append(video)
            outer_wrapper.append(video_wrapper)

            # Caption wrapper (if caption exists)
            if caption:
                caption_wrapper = soup.new_tag("span")
                caption_wrapper["class"] = ["caption-wrapper"]

                figcaption = soup.new_tag("figcaption")

                # Render caption as markdown if it's from metadata
                if metadata.get("caption"):
                    caption_html = render_markdown(caption, context=context)
                    caption_soup = BeautifulSoup(caption_html, "html.parser")

                    # Extract content from caption (remove wrapper <p> if it exists)
                    caption_content = caption_soup.find("p")
                    if caption_content:
                        # Move all children of <p> to figcaption
                        for child in list(caption_content.children):
                            figcaption.append(child)
                    else:
                        # Use the entire rendered content
                        for child in list(
                            caption_soup.body.children if caption_soup.body else []
                        ):
                            figcaption.append(child)
                else:
                    # Use existing caption HTML (already parsed from existing_caption)
                    caption_parsed = BeautifulSoup(caption, "html.parser")
                    for child in list(caption_parsed.children):
                        figcaption.append(child)

                caption_wrapper.append(figcaption)
                outer_wrapper.append(caption_wrapper)

            figure.append(outer_wrapper)

            # Insert the new figure where the old one was
            figure_parent.insert(figure_index, figure)

        else:
            # Get caption
            caption = metadata.get("caption", "")

            # Check if element is inside a <p> with element as only child (markdown default)
            element_parent = element.parent
            replace_parent = False
            element_parent_parent = None
            element_parent_index = None
            element_index = None

            if element_parent.name == "p":
                # Check if this is a standalone element paragraph
                text_content = "".join(
                    [
                        str(c)
                        for c in element_parent.children
                        if isinstance(c, NavigableString)
                    ]
                ).strip()
                other_elements = [
                    c
                    for c in element_parent.children
                    if c.name and c.name not in ["img", "video"]
                ]

                if not text_content and not other_elements:
                    # This is a standalone element, replace the <p> with <figure>
                    element_parent_parent = element_parent.parent
                    element_parent_index = element_parent_parent.contents.index(
                        element_parent
                    )
                    element_parent.extract()
                    element.extract()
                    replace_parent = True
                else:
                    # Mixed content, just extract element
                    element_index = element_parent.contents.index(element)
                    element.extract()
            else:
                element_index = element_parent.contents.index(element)
                element.extract()

            # Create figure structure
            figure = soup.new_tag("figure")
            # Combine extracted classes with 'block'
            all_classes = list(set(figure_classes + ["block"]))
            figure["class"] = all_classes

            # Create wrapper structure
            outer_wrapper = soup.new_tag("span")
            outer_wrapper["class"] = ["figure-outer-wrapper"]

            # Video wrapper (use "image-wrapper video" to match reference)
            video_wrapper = soup.new_tag("span")
            video_wrapper["class"] = ["image-wrapper", "video"]
            video_wrapper.append(video)
            outer_wrapper.append(video_wrapper)

            # Caption wrapper (if caption exists)
            if caption:
                caption_wrapper = soup.new_tag("span")
                caption_wrapper["class"] = ["caption-wrapper"]

                figcaption = soup.new_tag("figcaption")

                # Render caption as markdown
                caption_html = render_markdown(caption, context=context)
                caption_soup = BeautifulSoup(caption_html, "html.parser")

                # Extract content from caption (remove wrapper <p> if it exists)
                caption_content = caption_soup.find("p")
                if caption_content:
                    # Move all children of <p> to figcaption
                    for child in list(caption_content.children):
                        figcaption.append(child)
                else:
                    # Use the entire rendered content
                    for child in list(
                        caption_soup.body.children if caption_soup.body else []
                    ):
                        figcaption.append(child)

                caption_wrapper.append(figcaption)
                outer_wrapper.append(caption_wrapper)

            figure.append(outer_wrapper)

            # Insert figure in place of original element
            if replace_parent and element_parent_parent is not None:
                # We replaced the <p>, insert at parent level
                element_parent_parent.insert(element_parent_index, figure)
            else:
                # Insert where element was
                element_parent.insert(element_index, figure)

    return soup_to_html(context, soup)


def asset_video_enhancer_default(html: str, context: dict) -> str:
    """Register this in POSTPROCESSORS."""
    return enhance_video_assets(html, context)
