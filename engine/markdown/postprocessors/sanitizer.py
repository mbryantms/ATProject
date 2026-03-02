# core/markdown/postprocessors/sanitizer.py

import logging

logger = logging.getLogger(__name__)

ALLOWED_TAGS = {
    # text
    "p",
    "br",
    "wbr",
    "div",
    "span",
    "section",
    "article",
    "cite",
    "mark",
    "ins",
    "del",
    "sup",
    "sub",
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
    # inline formatting (bleach defaults)
    "b",
    "i",
    "u",
    "em",
    "strong",
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

ALLOWED_ATTRIBUTES = {
    "*": {"class", "id", "title"},
    "a": {"href", "title", "rel", "target"},
    "img": {"src", "alt", "title", "width", "height", "loading", "decoding"},
    "video": {
        "src",
        "width",
        "height",
        "controls",
        "preload",
        "loop",
        "muted",
        "autoplay",
        "poster",
    },
    "audio": {"src", "controls", "preload", "loop", "muted", "autoplay"},
    "source": {"src", "type"},
    "track": {"src", "kind", "srclang", "label", "default"},
    "code": {"class"},
    "pre": {"class"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
    "input": {"type", "checked", "disabled"},
    "button": {"type", "title"},
    "time": {"datetime"},
    "abbr": {"title"},
    "acronym": {"title"},
    "table": {"class"},
    "blockquote": {"class", "cite"},
    "cite": {"class"},
    "ol": {"start", "type", "class"},
    "ul": {"class"},
    "li": {"class"},
    "div": {"class"},
    "span": {"class"},
    # SVG attributes for inline icons
    "svg": {"xmlns", "viewBox", "role", "aria-hidden", "focusable"},
    "path": {"d", "fill", "stroke", "stroke-width"},
    "g": {"fill", "stroke", "stroke-width"},
    # MathML/MathJax attributes
    "math": {"xmlns", "display", "alttext"},
    "mrow": {"class"},
    "mi": {"mathvariant"},
    "mo": {
        "stretchy",
        "largeop",
        "movablelimits",
        "symmetric",
        "maxsize",
        "minsize",
        "form",
    },
    "mn": {"class"},
    "msup": {"class"},
    "msub": {"class"},
    "msubsup": {"class"},
    "mfrac": {"linethickness", "bevelled"},
    "msqrt": {"class"},
    "mroot": {"class"},
    "mtext": {"class"},
    "menclose": {"notation"},
    "mspace": {"width", "height", "depth"},
    "mtable": {"columnalign", "rowspacing", "columnspacing", "displaystyle"},
    "mtr": {"columnalign"},
    "mtd": {"columnalign", "rowspan", "colspan"},
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def sanitize_html(html, context):
    """
    Sanitize HTML output using nh3.
    This is the FIRST post-processor and should run before any other HTML modifications.
    """
    import nh3

    try:
        sanitized = nh3.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            url_schemes=ALLOWED_URL_SCHEMES,
            generic_attribute_prefixes={"data-", "aria-"},
            clean_content_tags={"script", "style"},
            link_rel="noopener noreferrer",
        )

        return sanitized

    except Exception as e:
        logger.error(f"nh3 sanitization failed: {e}", exc_info=True)
        return ""
