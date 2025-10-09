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


def enhance_video_assets(html: str, context: dict) -> str:
    """
    Enhance video assets with HTML5 video player and responsive features.

    Creates structure matching asset_image_enhancer for consistency.
    """
    # Lazy import to avoid circular import
    from engine.models import Asset
    from engine.markdown.renderer import render_markdown

    soup = BeautifulSoup(html, "html.parser")

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

        # Create video element
        video = soup.new_tag("video")
        video["controls"] = "controls"
        video["preload"] = "metadata"  # Load first frame to avoid black screen

        # Check for loop attribute from metadata
        if metadata.get("loop") in ["true", "1", "yes"]:
            video["loop"] = ""

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

        # Add display width to style (responsive)
        final_width = display_width if display_width else intrinsic_width
        if final_width:
            style_parts.append(f"max-width: {final_width}px")
            style_parts.append("width: 100%")

        # Optionally add display height
        if display_height and display_width:
            style_parts.append(f"height: {display_height}px")

        if style_parts:
            video["style"] = "; ".join(style_parts)

        # Add poster image if available
        poster_url = None
        if metadata.get("poster"):
            # Check if it's an asset key or direct URL
            if metadata["poster"].startswith("@asset:"):
                poster_key = metadata["poster"].replace("@asset:", "")
                try:
                    poster_asset = Asset.objects.get(key=poster_key)
                    poster_url = poster_asset.file.url
                except Asset.DoesNotExist:
                    pass
            else:
                poster_url = metadata["poster"]

        if poster_url:
            video["data-video-poster"] = poster_url
            video["poster"] = poster_url

        # Add source element
        source = soup.new_tag("source")
        source["src"] = base_url
        source["type"] = asset.mime_type or "video/mp4"
        video.append(source)

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
                    c for c in element_parent.children if c.name and c.name not in ["img", "video"]
                ]

                if not text_content and not other_elements:
                    # This is a standalone element, replace the <p> with <figure>
                    element_parent_parent = element_parent.parent
                    element_parent_index = element_parent_parent.contents.index(element_parent)
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

    return str(soup)


def asset_video_enhancer_default(html: str, context: dict) -> str:
    """Register this in POSTPROCESSORS."""
    return enhance_video_assets(html, context)
