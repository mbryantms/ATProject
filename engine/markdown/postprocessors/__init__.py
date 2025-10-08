# engine/markdown/postprocessors/__init__.py

from .admonition_enhancer import admonition_enhancer_default
from .asset_document_enhancer import asset_document_enhancer_default
from .asset_image_enhancer import asset_image_enhancer_default
from .asset_video_enhancer import asset_video_enhancer_default
from .block_marker import block_marker_default
from .blockquote_enhancer import blockquote_enhancer_default
from .columns_enhancer import columns_enhancer_default
from .date_enhancer_v2 import date_enhancer_v2_default
from .epigraph_enhancer import epigraph_enhancer_default
from .first_paragraph_marker import first_paragraph_marker_default
from .footnote_enhancer import footnote_enhancer_default
from .horizontal_rule_enhancer import horizontal_rule_enhancer_default
from .link_decorator import link_decorator_default
from .list_enhancer import list_enhancer_default
from .math_copy_button import math_copy_button_default
from .modify_external_links import modify_external_links

# from .embed_handler import handle_embeds
from .sanitizer import sanitize_html
from .table_enhancer import table_enhancer_default
from .typography_enhancer import typography_enhancer_default

# Import other postprocessors

POSTPROCESSORS = [
    sanitize_html,
    asset_image_enhancer_default,  # Enhance image assets with responsive features
    asset_video_enhancer_default,  # Enhance video assets with HTML5 video markup
    asset_document_enhancer_default,  # Enhance document/data assets with metadata
    list_enhancer_default,  # Enhance list elements with classes and structure
    blockquote_enhancer_default,  # Add nesting level classes to blockquotes
    epigraph_enhancer_default,  # Wrap and enhance epigraphs with proper structure
    admonition_enhancer_default,  # Enhance admonitions (tip, note, warning, error)
    columns_enhancer_default,  # Add "list" class to lists within multi-column divs
    table_enhancer_default,  # Wrap tables in proper structure with size classification
    horizontal_rule_enhancer_default,  # Add style classes to hr elements
    typography_enhancer_default,  # Typography enhancements (subsup pairs, etc.)
    date_enhancer_v2_default,  # Add years-ago subscripts to explicitly marked dates
    footnote_enhancer_default,  # Enhance footnotes with self-links and structure
    block_marker_default,  # Mark discrete content blocks with "block" class
    first_paragraph_marker_default,  # Mark first paragraph in each section
    link_decorator_default,  # Add icon data attributes to links
    modify_external_links,
    math_copy_button_default,  # Add copy buttons to display block math equations
    # handle_embeds,
    # optimize_images,
    # Order matters - they run sequentially
]


def apply_postprocessors(html, context):
    """Apply all postprocessors in order"""
    for processor in POSTPROCESSORS:
        html = processor(html, context)
    return html
