# core/markdown/postprocessors/sanitizer.py

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_bleach_config():
    """Cache bleach configuration for better performance."""
    try:
        import bleach
    except ImportError:
        logger.warning("bleach not installed - HTML sanitization disabled")
        return None, None, None

    allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS).union(
        {
            # text
            "p",
            "br",  # line breaks
            "wbr",  # word break opportunity
            "div",
            "span",
            "section",
            "article",
            "cite",
            "mark",
            "ins",
            "del",
            "sup",  # superscript (for footnotes)
            "sub",  # subscript
            # headings
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            # lists
            "ul",
            "ol",
            "li",
            "hr",
            "blockquote",
            "dl",
            "dt",
            "dd",
            # code
            "pre",
            "code",
            "kbd",
            "samp",
            "var",
            # tables
            "table",
            "thead",
            "tbody",
            "tfoot",
            "tr",
            "th",
            "td",
            "caption",
            "colgroup",
            "col",
            # media
            "img",
            "figure",
            "figcaption",
            "picture",
            "source",
            "video",
            "audio",
            "track",
            # svg inline icons
            "svg",
            "path",
            "g",
            # links and interactive
            "a",
            "button",
            # forms (for task lists)
            "input",
            "label",
            # semantic
            "time",
            "address",
            "abbr",
            "acronym",
            # math (MathJax/MathML)
            "math",
            "mrow",
            "mi",
            "mo",
            "mn",
            "msup",
            "msub",
            "msubsup",
            "mfrac",
            "msqrt",
            "mroot",
            "mtext",
            "menclose",
            "mspace",
            "mpadded",
            "mphantom",
            "mfenced",
            "mtable",
            "mtr",
            "mtd",
            "semantics",
            "annotation",
            "annotation-xml",
        }
    )

    allowed_attrs = {
        "*": ["class", "id", "title", "data-*", "aria-*"],
        "a": ["href", "title", "rel", "target"],
        "img": ["src", "alt", "title", "width", "height", "loading", "decoding"],
        "video": ["src", "width", "height", "controls", "preload", "loop", "muted", "autoplay", "poster"],
        "audio": ["src", "controls", "preload", "loop", "muted", "autoplay"],
        "source": ["src", "type"],
        "track": ["src", "kind", "srclang", "label", "default"],
        "code": ["class"],
        "pre": ["class"],
        "th": ["colspan", "rowspan", "scope"],
        "td": ["colspan", "rowspan"],
        "input": ["type", "checked", "disabled"],
        "button": ["type", "title"],
        "time": ["datetime"],
        "abbr": ["title"],
        "acronym": ["title"],
        "table": ["class"],
        "blockquote": ["class", "cite"],
        "cite": ["class"],
        "ol": ["start", "type", "class"],
        "ul": ["class"],
        "li": ["class"],
        "div": ["class"],
        "span": ["class"],
        # SVG attributes for inline icons
        "svg": ["xmlns", "viewBox", "role", "aria-hidden", "focusable"],
        "path": ["d", "fill", "stroke", "stroke-width"],
        "g": ["fill", "stroke", "stroke-width"],
        # MathML/MathJax attributes
        "math": ["xmlns", "display", "alttext"],
        "mrow": ["class"],
        "mi": ["mathvariant"],
        "mo": ["stretchy", "largeop", "movablelimits", "symmetric", "maxsize", "minsize", "form"],
        "mn": ["class"],
        "msup": ["class"],
        "msub": ["class"],
        "msubsup": ["class"],
        "mfrac": ["linethickness", "bevelled"],
        "msqrt": ["class"],
        "mroot": ["class"],
        "mtext": ["class"],
        "menclose": ["notation"],
        "mspace": ["width", "height", "depth"],
        "mtable": ["columnalign", "rowspacing", "columnspacing", "displaystyle"],
        "mtr": ["columnalign"],
        "mtd": ["columnalign", "rowspan", "colspan"],
    }

    allowed_protocols = ["http", "https", "mailto", "tel"]

    return allowed_tags, allowed_attrs, allowed_protocols


def sanitize_html(html, context):
    """
    Sanitize HTML output using bleach.
    This is the FIRST post-processor and should run before any other HTML modifications.
    """
    config = _get_bleach_config()
    if not config[0]:  # bleach not available
        logger.debug("Bleach unavailable, skipping sanitization")
        return html

    allowed_tags, allowed_attrs, allowed_protocols = config

    try:
        import bleach

        sanitized = bleach.clean(
            html,
            tags=allowed_tags,
            attributes=allowed_attrs,
            protocols=allowed_protocols,
            strip=False,  # Keep disallowed tags but strip their attributes
        )

        return sanitized

    except Exception as e:
        logger.error(f"Bleach sanitization failed: {e}", exc_info=True)
        # On failure, return original HTML - you may want different behavior
        return html
