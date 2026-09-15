"""
Postprocessor that turns a ``::: {.gallery}`` fenced div into a gallery block.

Authors write several image references inside one fenced div, one per
paragraph, optionally followed by a paragraph that becomes the gallery's own
caption::

    ::: {.gallery .wall row-height=tall}

    ![Low tide](@asset:bolinas-low-tide)

    ![Fog on the ridge](@fog-ridge)

    **Point Reyes, February.** Twelve frames from one walk.

    :::

Pandoc emits ``<div class="gallery wall" data-row-height="tall">`` with one
``<figure>`` per image, which the image enhancer has already turned into the
site's standard figure markup by the time this runs. This postprocessor:

- picks the layout (``wall`` default, ``grid``, ``strip``) and validates the
  ``row-height=`` / ``columns=`` / ``captions=`` attributes, filling
  ``row-height`` from ``settings.GALLERY_ROW_HEIGHT`` when the author gave none
  (``rows``/``cols`` would collide with real HTML attribute names, which
  Pandoc passes through verbatim and the sanitizer then strips);
- moves the figures into ``div.gallery-items`` (the flex/grid container) and
  marks each ``figure.gallery-item``, dropping the ``block`` spacing class a
  lone figure would carry;
- copies each image's aspect ratio onto its figure as ``--ar`` so CSS and the
  wall-sizing script can lay tiles out before the image loads;
- folds the asset title (stamped as ``data-title`` by the image enhancer) into
  the tile caption as a bold first line, creating the caption if needed;
- turns a trailing paragraph into ``figcaption.gallery-caption``.

Nothing here touches figures outside a gallery, and the tile figures keep the
exact markup the image-focus viewer expects, so the existing lightbox works on
them unchanged.
"""

from django.conf import settings

from .utils import get_shared_soup, soup_to_html

GALLERY_LAYOUTS = ("wall", "grid", "strip")
ROW_PRESETS = ("auto", "short", "medium", "tall")
CAPTION_MODES = ("hover", "under", "viewer")
_ROW_PX_MIN, _ROW_PX_MAX = 80, 800
_COLS_MIN, _COLS_MAX, _COLS_DEFAULT = 2, 6, 3


def normalize_rows(value) -> str | None:
    """Return a valid ``row-height`` value (preset or pixel count) or ``None``."""
    text = str(value or "").strip().lower()
    if text in ROW_PRESETS:
        return text
    if text.isdigit() and _ROW_PX_MIN <= int(text) <= _ROW_PX_MAX:
        return text
    return None


def normalize_cols(value) -> int | None:
    text = str(value or "").strip()
    if text.isdigit() and _COLS_MIN <= int(text) <= _COLS_MAX:
        return int(text)
    return None


def _classes(tag) -> list[str]:
    raw = tag.get("class") or []
    return raw.split() if isinstance(raw, str) else list(raw)


def _aspect_ratio(figure) -> float | None:
    img = figure.find("img")
    if img is None:
        return None
    ratio = img.get("data-aspect-ratio")
    if ratio and "/" in ratio:
        w, _, h = ratio.partition("/")
        try:
            w, h = float(w.strip()), float(h.strip())
        except ValueError:
            return None
        if w > 0 and h > 0:
            return w / h
    w, h = img.get("width"), img.get("height")
    try:
        w, h = float(w), float(h)
    except TypeError, ValueError:
        return None
    return w / h if w > 0 and h > 0 else None


def _append_style(tag, declaration: str) -> None:
    existing = (tag.get("style") or "").strip().rstrip(";")
    tag["style"] = f"{existing}; {declaration}" if existing else declaration


def _fold_title_into_caption(soup, figure) -> None:
    title = (figure.get("data-title") or "").strip()
    if figure.has_attr("data-title"):
        del figure["data-title"]
    if not title:
        return

    heading = soup.new_tag("b")
    heading["class"] = ["figure-title"]
    heading.string = title

    figcaption = figure.find("figcaption")
    if figcaption is not None:
        figcaption.insert(0, heading)
        return

    outer = figure.find("span", class_="figure-outer-wrapper")
    if outer is None:
        return
    caption_wrapper = soup.new_tag("span")
    caption_wrapper["class"] = ["caption-wrapper"]
    figcaption = soup.new_tag("figcaption")
    figcaption.append(heading)
    caption_wrapper.append(figcaption)
    outer.append(caption_wrapper)


def enhance_galleries(html: str, context: dict) -> str:
    soup = get_shared_soup(html, context)

    default_rows = normalize_rows(getattr(settings, "GALLERY_ROW_HEIGHT", "auto"))
    default_rows = default_rows or "auto"

    for wrapper in soup.find_all("div", class_="gallery"):
        classes = _classes(wrapper)
        layout = next((c for c in classes if c in GALLERY_LAYOUTS), "wall")
        if layout not in classes:
            classes.append(layout)
        wrapper["class"] = classes

        rows = normalize_rows(wrapper.get("data-row-height")) or default_rows
        wrapper["data-row-height"] = rows
        cols = normalize_cols(wrapper.get("data-columns")) or _COLS_DEFAULT
        wrapper["data-columns"] = str(cols)
        captions = str(wrapper.get("data-captions") or "").strip().lower()
        wrapper["data-captions"] = captions if captions in CAPTION_MODES else "hover"

        style = [f"--cols: {cols}"]
        if rows.isdigit():
            style.append(f"--row-base: {rows}px")
        wrapper["style"] = "; ".join(style)

        figures = wrapper.find_all("figure", recursive=False)

        # A paragraph after the last figure is the gallery's own caption.
        gallery_caption = None
        block_children = [c for c in wrapper.contents if getattr(c, "name", None)]
        if figures and block_children and block_children[-1].name == "p":
            paragraph = block_children[-1]
            gallery_caption = soup.new_tag("figcaption")
            gallery_caption["class"] = ["gallery-caption"]
            for child in list(paragraph.children):
                gallery_caption.append(child)
            paragraph.decompose()

        items = soup.new_tag("div")
        items["class"] = ["gallery-items"]
        for figure in figures:
            figure.extract()
            fig_classes = [c for c in _classes(figure) if c != "block"]
            if "gallery-item" not in fig_classes:
                fig_classes.append("gallery-item")
            figure["class"] = fig_classes

            ratio = _aspect_ratio(figure)
            if ratio:
                _append_style(figure, f"--ar: {ratio:.4f}")

            _fold_title_into_caption(soup, figure)
            items.append(figure)

        wrapper.append(items)
        if gallery_caption is not None:
            wrapper.append(gallery_caption)
        wrapper["data-count"] = str(len(figures))

    return soup_to_html(context, soup)


def gallery_enhancer_default(html: str, context: dict) -> str:
    """Register this in POSTPROCESSORS (after the image enhancer)."""
    return enhance_galleries(html, context)
