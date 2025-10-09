"""
Postprocessor that enhances image assets with responsive features.

Adds:
- srcset for responsive images (using AssetRenditions)
- loading="lazy" for performance
- Figure wrappers with captions
- Proper sizing attributes
- Enhanced structure matching reference design
"""

import urllib.parse
from math import gcd

from bs4 import BeautifulSoup, NavigableString


def enhance_image_assets(html: str, context: dict) -> str:
    """
    Enhance image assets with responsive attributes and lazy loading.

    Creates structure:
    <figure class="float-right float block" style="--bsm: 10;">
      <span class="figure-outer-wrapper">
        <span class="image-wrapper img focusable">

          <img ...>
        </span>
        <span class="caption-wrapper">
          <figcaption>...</figcaption>
        </span>
      </span>
    </figure>
    """
    # Lazy import to avoid circular import
    from engine.markdown.renderer import render_markdown
    from engine.models import Asset

    soup = BeautifulSoup(html, "html.parser")

    # Find all images with asset metadata
    for img in list(soup.find_all("img")):
        src = img.get("src", "")

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

        if asset_type != "image":
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

        # Get asset for renditions
        try:
            asset = Asset.objects.get(key=asset_key)
        except Asset.DoesNotExist:
            continue

        # Clean up src (remove metadata)
        img["src"] = base_url

        # Determine intrinsic dimensions (actual image size)
        intrinsic_width = (
            int(metadata.get("width")) if metadata.get("width") else asset.width
        )
        intrinsic_height = (
            int(metadata.get("height")) if metadata.get("height") else asset.height
        )

        # Check for display size overrides (from query params like ?width=800)
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

        # If only display_width is specified, calculate proportional display_height
        if (
            display_width
            and not display_height
            and intrinsic_width
            and intrinsic_height
        ):
            display_height = int((display_width / intrinsic_width) * intrinsic_height)
        # If only display_height is specified, calculate proportional display_width
        elif (
            display_height
            and not display_width
            and intrinsic_width
            and intrinsic_height
        ):
            display_width = int((display_height / intrinsic_height) * intrinsic_width)

        # Add intrinsic dimensions to img attributes (what the browser knows about the actual image)
        if intrinsic_width:
            img["width"] = intrinsic_width
        if intrinsic_height:
            img["height"] = intrinsic_height

        # Calculate aspect ratio and add style
        aspect_ratio = None
        style_parts = []

        if intrinsic_width and intrinsic_height:
            # Simplify aspect ratio based on intrinsic dimensions
            divisor = gcd(intrinsic_width, intrinsic_height)
            aspect_w = intrinsic_width // divisor
            aspect_h = intrinsic_height // divisor
            aspect_ratio = f"{aspect_w} / {aspect_h}"

            img["data-aspect-ratio"] = aspect_ratio
            style_parts.append(f"aspect-ratio: {aspect_w} / {aspect_h}")

        # Add display width to style (use display_width if specified, otherwise intrinsic_width)
        final_width = display_width if display_width else intrinsic_width
        if final_width:
            style_parts.append(f"width: {final_width}px")

        # Optionally add display height (uncommon, but supported)
        if display_height and display_width:
            # Only add explicit height if both display dimensions are specified
            style_parts.append(f"height: {display_height}px")

        # Combine with any existing style
        if style_parts:
            existing_style = img.get("style", "").strip()
            if existing_style and not existing_style.endswith(";"):
                existing_style += ";"
            img["style"] = "; ".join(style_parts) + (
                "" if not existing_style else f"; {existing_style}"
            )

        # Add responsive srcset from renditions
        renditions = asset.renditions.filter(format="auto").order_by("width")
        if renditions.exists():
            srcset_parts = []
            for rendition in renditions:
                srcset_parts.append(f"{rendition.file.url} {rendition.width}w")

            if srcset_parts:
                img["srcset"] = ", ".join(srcset_parts)

                # Add sizes attribute (can be customized)
                img["sizes"] = "(max-width: 649px) 100vw, 935px"

        # Add lazy loading
        if not img.get("loading"):
            img["loading"] = "lazy"

        # Add decoding hint
        if not img.get("decoding"):
            img["decoding"] = "async"

        # Add alt text if missing (from metadata or asset)
        if not img.get("alt"):
            img["alt"] = metadata.get("alt_text", asset.alt_text or "")

        # Extract existing classes from img (Pandoc puts attributes on img tag)
        existing_img_classes = []
        if img.get("class"):
            if isinstance(img["class"], list):
                existing_img_classes = img["class"]
            else:
                existing_img_classes = img["class"].split()

        # Separate positioning classes from image styling classes
        positioning_classes = [
            "float-right",
            "float-left",
            "float-center",
            "width-full",
            "inline",
        ]
        figure_classes = [
            cls for cls in existing_img_classes if cls in positioning_classes
        ]
        img_only_classes = [
            cls for cls in existing_img_classes if cls not in positioning_classes
        ]

        # Add standard image classes
        img_classes = ["focusable", "gallery-image"] + img_only_classes

        # Check for invert class in alt text or metadata
        if "invert" in img.get("alt", "").lower():
            if "invert" not in img_classes:
                img_classes.append("invert")

        # Update img classes (without positioning classes)
        img["class"] = img_classes

        # Check if already wrapped in a markdown-generated figure
        existing_figure = None
        if img.parent.name == "figure":
            existing_figure = img.parent
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

            # Extract the img element
            img.extract()

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

            # Image wrapper
            image_wrapper = soup.new_tag("span")
            image_wrapper["class"] = ["image-wrapper", "img", "focusable"]
            image_wrapper.append(img)
            outer_wrapper.append(image_wrapper)

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
                    # Caption is already HTML string from line 215
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

            # Check if img is inside a <p> with <img> as only child (markdown default)
            img_parent = img.parent
            replace_parent = (
                False  # Flag to track if we're replacing the parent element
            )
            img_parent_parent = None
            img_parent_index = None
            img_index = None

            if img_parent.name == "p":
                # Check if this is a standalone image paragraph
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
                    # This is a standalone image, replace the <p> with <figure>
                    img_parent_parent = img_parent.parent
                    img_parent_index = img_parent_parent.contents.index(img_parent)
                    img_parent.extract()
                    img.extract()
                    replace_parent = True
                else:
                    # Mixed content, just extract img
                    img_index = img_parent.contents.index(img)
                    img.extract()
            else:
                img_index = img_parent.contents.index(img)
                img.extract()

            # Create figure structure
            figure = soup.new_tag("figure")
            # Combine extracted classes with 'block'
            all_classes = list(set(figure_classes + ["block"]))
            figure["class"] = all_classes

            # Create wrapper structure
            outer_wrapper = soup.new_tag("span")
            outer_wrapper["class"] = ["figure-outer-wrapper"]

            # Image wrapper
            image_wrapper = soup.new_tag("span")
            image_wrapper["class"] = ["image-wrapper", "img", "focusable"]
            image_wrapper.append(img)
            outer_wrapper.append(image_wrapper)

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
            if replace_parent and img_parent_parent is not None:
                # We replaced the <p>, insert at parent level
                img_parent_parent.insert(img_parent_index, figure)
            else:
                # Insert where img was
                img_parent.insert(img_index, figure)

    return str(soup)


def asset_image_enhancer_default(html: str, context: dict) -> str:
    """Register this in POSTPROCESSORS."""
    return enhance_image_assets(html, context)
