"""
Reusable admin form widgets for CharFields whose values are free-typed but
whose sensible value space is known: hex colors, icon glyphs, and fields
with a suggestion list (e.g. IETF language tags).

All widgets keep the underlying field a plain CharField — unusual values can
still be typed or set via the ORM; the widgets just make the common choices
one click instead of something to remember and retype. Chrome is styled on
Django admin's own CSS variables (css/admin-widgets.css) so both admin
themes match.
"""

from django import forms
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join, json_script

from engine.icons import SPRITE_STATIC_PATH, lucide_icon_names

# Muted preset swatches shown as a clickable row beside the color dialog.
# Chosen to sit well against the site's monochrome ground; any other color
# can still be picked in the native dialog or typed as hex.
COLOR_PRESETS = [
    "#8A6D3B",  # ochre
    "#A33B2E",  # brick
    "#B45309",  # rust
    "#7F1D1D",  # oxblood
    "#4D7C0F",  # moss
    "#166534",  # pine
    "#0F766E",  # teal
    "#3B6D8A",  # steel blue
    "#1E40AF",  # ultramarine
    "#5B21B6",  # violet
    "#86198F",  # plum
    "#9D174D",  # mulberry
    "#374151",  # slate
    "#6B7280",  # grey (Tag default)
    "#3B82F6",  # azure (AssetTag default)
]

# Typographic marks and emoji offered alongside the Lucide set — these render
# as literal text on the public site, so they remain first-class values.
GLYPH_GROUPS = [
    (
        "Marks",
        [
            "¶",
            "§",
            "†",
            "‡",
            "※",
            "⁂",
            "❧",
            "☞",
            "✱",
            "✦",
            "✧",
            "★",
            "☆",
            "❖",
            "◆",
            "◇",
            "●",
            "○",
            "■",
            "□",
            "▲",
            "△",
            "◉",
            "⊙",
            "∞",
            "∴",
            "≡",
            "⌘",
            "&",
            "@",
        ],
    ),
    (
        "Emoji",
        [
            "📐",
            "🏛️",
            "📚",
            "📖",
            "🗺️",
            "🧭",
            "✏️",
            "🖋️",
            "🔧",
            "🛠️",
            "🎨",
            "📷",
            "🎞️",
            "🎵",
            "💻",
            "⌨️",
            "🔬",
            "🧪",
            "🌿",
            "🌍",
            "⚖️",
            "🕰️",
            "🏗️",
            "🧱",
            "📜",
            "🗿",
            "⛪",
            "🏰",
            "🌉",
            "🔭",
        ],
    ),
]

# Common IETF language tags surfaced as datalist suggestions.
LANGUAGE_SUGGESTIONS = [
    ("en", "English"),
    ("en-GB", "English (UK)"),
    ("de", "German"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("nl", "Dutch"),
    ("sv", "Swedish"),
    ("ru", "Russian"),
    ("zh-CN", "Chinese (Simplified)"),
    ("zh-TW", "Chinese (Traditional)"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("ar", "Arabic"),
    ("he", "Hebrew"),
    ("la", "Latin"),
    ("grc", "Ancient Greek"),
]


class ColorInput(forms.TextInput):
    """Native color dialog + synced hex readout + a visible preset row.

    The color input carries the form value; the hex text field and the
    swatch buttons are conveniences kept in sync by admin-widgets.js.
    """

    input_type = "color"

    class Media:
        css = {"all": ("css/admin-widgets.css",)}
        js = ("js/admin-widgets.js",)

    def __init__(self, attrs=None, presets=None):
        self.presets = COLOR_PRESETS if presets is None else presets
        base = {"class": "mk-color-input"}
        if attrs:
            base.update(attrs)
        super().__init__(base)

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        swatches = format_html_join(
            "",
            '<button type="button" class="mk-color-swatch" data-color="{0}" '
            'style="background-color:{0}" title="{0}"></button>',
            ((c,) for c in self.presets),
        )
        return format_html(
            '<span class="mk-color-picker">'
            "{}"
            '<input type="text" class="mk-color-hex" value="{}" maxlength="7" '
            'size="8" spellcheck="false" aria-label="Hex color value">'
            '<span class="mk-color-swatches" role="group" '
            'aria-label="Preset colors">{}</span>'
            "</span>",
            input_html,
            value or "",
            swatches,
        )


class DatalistTextInput(forms.TextInput):
    """Text input with ``<datalist>`` suggestions — a permissive select.

    ``options`` is an iterable of ``(value, label)`` pairs or bare values.
    """

    def __init__(self, options, attrs=None):
        self.options = [o if isinstance(o, tuple) else (o, "") for o in options]
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        list_id = f"{attrs.get('id', 'id_' + name)}_options"
        attrs["list"] = list_id
        input_html = super().render(name, value, attrs, renderer)
        options = format_html_join(
            "", '<option value="{}" label="{}"></option>', self.options
        )
        return format_html(
            '{}<datalist id="{}">{}</datalist>', input_html, list_id, options
        )


class GlyphPickerInput(forms.TextInput):
    """Text input with a searchable popover palette of icons.

    Offers typographic marks and emoji (stored as literal text) plus the
    full vendored Lucide set (stored as ``lucide:<name>`` and rendered as
    inline SVG by engine.icons). The Lucide grid is built lazily by
    admin-widgets.js from the name list embedded via ``json_script`` — the
    server never renders ~1,700 buttons into the page. Values remain
    free-typed; anything can still be entered by hand.
    """

    class Media:
        css = {"all": ("css/admin-widgets.css",)}
        js = ("js/admin-widgets.js",)

    def __init__(self, attrs=None, glyph_groups=None):
        self.glyph_groups = GLYPH_GROUPS if glyph_groups is None else glyph_groups
        base = {"class": "mk-glyph-input"}
        if attrs:
            base.update(attrs)
        super().__init__(base)

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        widget_id = (attrs or {}).get("id", f"id_{name}")
        groups = format_html_join(
            "",
            '<div class="mk-glyph-group">'
            '<span class="mk-glyph-group-label">{}</span>'
            '<div class="mk-glyph-grid">{}</div>'
            "</div>",
            (
                (
                    label,
                    format_html_join(
                        "",
                        '<button type="button" class="mk-glyph-option" '
                        'data-glyph="{0}" title="{0}">{0}</button>',
                        ((g,) for g in glyphs),
                    ),
                )
                for label, glyphs in self.glyph_groups
            ),
        )
        names = json_script(list(lucide_icon_names()), f"{widget_id}_lucide_names")
        return format_html(
            '<span class="mk-glyph-picker" data-sprite-url="{}">'
            "{}"
            '<span class="mk-glyph-preview" aria-hidden="true"></span>'
            '<button type="button" class="mk-glyph-toggle button" '
            'aria-expanded="false" aria-haspopup="true">Choose…</button>'
            '<div class="mk-glyph-panel" hidden>'
            '<input type="search" class="mk-glyph-search" '
            'placeholder="Search icons…" aria-label="Search icons">'
            "{}"
            '<div class="mk-glyph-group">'
            '<span class="mk-glyph-group-label">Icons (Lucide)</span>'
            '<div class="mk-glyph-grid mk-glyph-grid-lucide" data-lucide-grid>'
            "</div></div>"
            '<button type="button" class="mk-glyph-clear button">'
            "Clear icon</button>"
            "</div>"
            "{}"
            "</span>",
            static(SPRITE_STATIC_PATH),
            input_html,
            groups,
            names,
        )
