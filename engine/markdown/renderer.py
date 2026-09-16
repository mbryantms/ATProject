# core/markdown/renderer.py

import pypandoc

from .config import get_pandoc_config
from .postprocessors import apply_postprocessors
from .preprocessors import apply_preprocessors


def render_markdown(text, context=None):
    """
    Main rendering function with pre/post processing pipeline using pypandoc

    Args:
        text: Raw markdown text
        context: Optional dict for processors that need additional data
    """
    context = context or {}

    # Pre-processing: Before markdown conversion
    text = apply_preprocessors(text, context)

    # Markdown conversion using pypandoc
    pandoc_config = get_pandoc_config()

    html = pypandoc.convert_text(
        text,
        to="html5",
        format="markdown",
        extra_args=pandoc_config["extra_args"],
        filters=pandoc_config.get("filters", []),
    )

    # Post-processing: After markdown conversion
    html = apply_postprocessors(html, context)

    return html


def render_markdown_fragment(text, context):
    """
    Render a nested fragment (an image or video caption) with the parent
    document's context.

    Sets ``context["fragment"]`` for the duration so postprocessors that only
    make sense for a whole document (the automatic dropcap on the opening
    paragraph) leave the fragment alone.
    """
    previous = context.get("fragment")
    context["fragment"] = True
    try:
        return render_markdown(text, context=context)
    finally:
        if previous is None:
            context.pop("fragment", None)
        else:
            context["fragment"] = previous
