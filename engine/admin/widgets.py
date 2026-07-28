"""
Reusable admin form widgets for CharFields whose values are free-typed but
whose sensible value space is known: hex colors, icon glyphs, and fields
with a suggestion list (e.g. IETF language tags).

All widgets keep the underlying field a plain CharField — unusual values can
still be typed or set via the ORM; the widgets just make the common choices
one click instead of something to remember and retype.
"""

from django import forms
from django.utils.html import format_html, format_html_join

# Muted preset swatches offered inside the native color-picker dialog.
# Chosen to sit well against the site's monochrome ground; any other color
# can still be picked freely in the dialog.
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

# Curated glyph palette for icon fields. The templates render the value as
# text, so anything typeable works — these are just the likely wants.
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
    """Native color picker with preset swatches.

    Renders ``<input type="color" list="…">`` plus a ``<datalist>`` of preset
    hexes — supporting browsers show the presets as swatches inside the
    picker dialog; others just show the plain picker.
    """

    input_type = "color"

    class Media:
        css = {"all": ("css/admin-widgets.css",)}

    def __init__(self, attrs=None, presets=None):
        self.presets = COLOR_PRESETS if presets is None else presets
        base = {"class": "mk-color-input"}
        if attrs:
            base.update(attrs)
        super().__init__(base)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        list_id = f"{attrs.get('id', 'id_' + name)}_presets"
        attrs["list"] = list_id
        input_html = super().render(name, value, attrs, renderer)
        options = format_html_join(
            "", '<option value="{}"></option>', ((c,) for c in self.presets)
        )
        return format_html(
            '{}<datalist id="{}">{}</datalist>', input_html, list_id, options
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
    """Text input with a popover palette of curated glyphs.

    The value stays free-typed (any emoji, symbol, or icon name works); the
    palette makes the common choices one click. Behavior lives in
    static/js/admin-widgets.js — an external file so the nonce CSP doesn't
    block it.
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
        return format_html(
            '<span class="mk-glyph-picker">'
            "{}"
            '<button type="button" class="mk-glyph-toggle" aria-expanded="false" '
            'aria-haspopup="true">Pick…</button>'
            '<div class="mk-glyph-panel" hidden>'
            "{}"
            '<button type="button" class="mk-glyph-clear">Clear icon</button>'
            "</div>"
            "</span>",
            input_html,
            groups,
        )
