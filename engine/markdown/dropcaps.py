"""
Dropcap style registry.

The single source of truth for every dropcap style the site offers. Model
choices, the admin pickers, the markdown cheatsheet, the postprocessor and
the generated stylesheet (``static/css/src/dropcaps.css``, built by
``manage.py generate_dropcaps_css``) all read from ``STYLES``.

How a dropcap is resolved, nearest wins:

1. ``::: {.dropcap-<key>}`` around a paragraph in the markdown.
2. ``Post.dropcap_style`` / ``Page.dropcap_style`` for the document's
   opening paragraph (``INHERIT`` defers to the site, ``NONE`` switches
   it off).
3. ``SiteSettings.default_dropcap_style`` (blank = off).

The document-level style is applied as a class on the ``.markdownBody``
wrapper at request time, not baked into the cached HTML, so changing the
site default or a post's setting takes effect without re-rendering. The
postprocessor only hoists the opening letter into an inert
``span.dropcap-letter``; the CSS custom properties set by the wrapper or
paragraph class are what make it a dropcap.

Every style here ships under a licence that permits web embedding; the
licence text lives next to the font in ``static/font/dropcap/<key>/``.
"""

from __future__ import annotations

from dataclasses import dataclass

INHERIT = ""
NONE = "none"
CLASS_PREFIX = "dropcap-"
DEFAULT_LINES = 3
MIN_LINES = 2
MAX_LINES = 6

# Groups, in picker order.
GROUPS = (
    ("classic", "Classic & Roman"),
    ("blackletter", "Blackletter & Medieval"),
    ("calligraphic", "Calligraphic"),
    ("script", "Script"),
    ("display", "Display & Decorative"),
)


@dataclass(frozen=True)
class DropcapStyle:
    key: str
    label: str
    family: str
    group: str
    file: str = ""
    weight: int = 400
    variable: bool = False
    """Variable-weight face; the @font-face declares the full 100-900 range."""
    scale: float = 1.0
    """Multiplier on the computed drop size; tunes fonts with unusual cap
    heights so the letter still spans ``lines`` lines."""
    nudge: float = 0.0
    """Extra top offset in em of the letter's own font size; pushes glyphs
    with tall ascenders down onto the cap line."""
    gap: float = 0.1
    """Space between the letter and the text, in em of the letter's font
    size; scripts with swashes that overrun their advance width need more."""
    license: str = "OFL-1.1"
    description: str = ""

    @property
    def css_class(self) -> str:
        return f"{CLASS_PREFIX}{self.key}"

    @property
    def font_path(self) -> str:
        return f"/static/font/dropcap/{self.key}/{self.file or self.key + '.woff2'}"


def _s(key, label, family, group, **kw) -> DropcapStyle:
    return DropcapStyle(key=key, label=label, family=family, group=group, **kw)


STYLES: tuple[DropcapStyle, ...] = (
    # Classic & Roman
    _s(
        "cinzel",
        "Cinzel",
        "Cinzel",
        "classic",
        variable=True,
        weight=700,
        scale=1.05,
        description="Roman inscriptional capitals.",
    ),
    _s(
        "cinzel-decorative",
        "Cinzel Decorative",
        "Cinzel Decorative",
        "classic",
        scale=1.0,
        description="Inscriptional capitals with flourishes.",
    ),
    _s(
        "cormorant-garamond",
        "Cormorant Garamond",
        "Cormorant Garamond",
        "classic",
        variable=True,
        weight=600,
        scale=1.08,
        description="Elegant Garamond with sharp serifs.",
    ),
    _s(
        "playfair-display",
        "Playfair Display",
        "Playfair Display",
        "classic",
        variable=True,
        weight=700,
        scale=1.05,
        description="High-contrast transitional display.",
    ),
    _s(
        "cardo",
        "Cardo",
        "Cardo",
        "classic",
        weight=700,
        scale=1.06,
        description="Bembo-style scholarly serif.",
    ),
    _s(
        "im-fell-english",
        "IM Fell English",
        "IM Fell English",
        "classic",
        scale=1.08,
        description="Seventeenth-century Fell types.",
    ),
    _s(
        "decorated-roman-initials",
        "Decorated Roman Initials",
        "Decorated Roman Initials",
        "classic",
        license="Freeware (Dieter Steffmann)",
        description="Decorated roman initials.",
    ),
    # Blackletter & Medieval
    _s(
        "unifraktur-maguntia",
        "UnifrakturMaguntia",
        "UnifrakturMaguntia",
        "blackletter",
        scale=1.02,
        description="Textura-derived fraktur.",
    ),
    _s(
        "grenze-gotisch",
        "Grenze Gotisch",
        "Grenze Gotisch",
        "blackletter",
        variable=True,
        weight=500,
        scale=1.0,
        description="Contemporary blackletter.",
    ),
    _s(
        "new-rocker",
        "New Rocker",
        "New Rocker",
        "blackletter",
        scale=1.0,
        description="Rock-poster blackletter.",
    ),
    _s(
        "fruktur",
        "Fruktur",
        "Fruktur",
        "blackletter",
        scale=1.0,
        description="Playful fraktur-inspired display.",
    ),
    _s(
        "astloch",
        "Astloch",
        "Astloch",
        "blackletter",
        weight=700,
        scale=1.0,
        description="Light hairline gothic.",
    ),
    _s(
        "kanzlei-initialen",
        "Kanzlei Initialen",
        "Kanzlei Initialen",
        "blackletter",
        license="Freeware (Dieter Steffmann)",
        scale=1.1,
        gap=0.14,
        description="Chancery blackletter initials.",
    ),
    _s(
        "koenigsberger-gotisch",
        "Koenigsberger Gotisch",
        "Koenigsberger Gotisch",
        "blackletter",
        license="Freeware (Dieter Steffmann)",
        scale=1.05,
        description="Königsberg gothic.",
    ),
    _s(
        "grusskarten-gotisch",
        "Grusskarten Gotisch",
        "Grusskarten Gotisch",
        "blackletter",
        license="Freeware (Dieter Steffmann)",
        description="Greeting-card gothic.",
    ),
    _s(
        "hansa-gotisch",
        "Hansa Gotisch",
        "Hansa Gotisch",
        "blackletter",
        license="Freeware (Dieter Steffmann)",
        description="Hanseatic gothic.",
    ),
    _s(
        "hermann-gotisch",
        "Hermann Gotisch",
        "Hermann Gotisch",
        "blackletter",
        license="Freeware (Dieter Steffmann)",
        description="Hermann gothic.",
    ),
    _s(
        "westminster-gotisch",
        "Westminster Gotisch",
        "Westminster Gotisch",
        "blackletter",
        license="Freeware (Dieter Steffmann)",
        description="Westminster gothic.",
    ),
    # Calligraphic
    _s(
        "berkshire-swash",
        "Berkshire Swash",
        "Berkshire Swash",
        "calligraphic",
        scale=1.02,
        gap=0.16,
        description="Swashed roman capitals.",
    ),
    _s(
        "romantik",
        "Romantik",
        "Romantik",
        "calligraphic",
        license="Freeware (Dieter Steffmann)",
        scale=1.1,
        gap=0.14,
        description="Romantic decorated script capitals.",
    ),
    _s(
        "coelnische-current",
        "Coelnische Current",
        "Coelnische Current",
        "calligraphic",
        license="Freeware (Dieter Steffmann)",
        description="Cologne Kurrent hand.",
    ),
    _s(
        "paulus-franck-initialen",
        "Paulus Franck Initialen",
        "Paulus Franck Initialen",
        "calligraphic",
        license="Freeware (Dieter Steffmann)",
        scale=1.05,
        gap=0.16,
        description="After Paulus Franck's 1601 calligraphic initials.",
    ),
    # Script
    _s(
        "lobster",
        "Lobster",
        "Lobster",
        "script",
        scale=1.0,
        description="Bold retro script.",
    ),
    # Display & Decorative
    _s(
        "rye",
        "Rye",
        "Rye",
        "display",
        scale=0.98,
        description="Western wood-type display.",
    ),
    _s(
        "emblema-one",
        "Emblema One",
        "Emblema One",
        "display",
        scale=0.98,
        description="Inline outlined capitals.",
    ),
    _s(
        "monoton",
        "Monoton",
        "Monoton",
        "display",
        scale=0.98,
        description="Art-deco lined display.",
    ),
    _s(
        "limelight",
        "Limelight",
        "Limelight",
        "display",
        scale=1.0,
        description="Art-deco high-contrast display.",
    ),
    _s(
        "lettres-ombrees-ornees",
        "Lettres Ombrées Ornées",
        "Lettres Ombrées Ornées",
        "display",
        license="Freeware (Dieter Steffmann)",
        scale=1.1,
        gap=0.14,
        description="Shaded, ornamented French capitals.",
    ),
    _s(
        "acorn-initials",
        "Acorn Initials",
        "Acorn Initials",
        "display",
        license="Freeware (Dieter Steffmann)",
        gap=0.14,
        description="Initials wreathed in oak leaves and acorns.",
    ),
    _s(
        "arabesque-initialen",
        "Arabesque Initialen",
        "Arabesque Initialen",
        "display",
        license="Freeware (Dieter Steffmann)",
        scale=0.95,
        gap=0.16,
        description="Initials on arabesque grounds.",
    ),
    _s(
        "typographer-woodcut",
        "Typographer Woodcut Initials",
        "Typographer Woodcut Initials",
        "display",
        license="Freeware (Dieter Steffmann)",
        scale=0.8,
        gap=0.16,
        description="Woodcut-style initials.",
    ),
    _s(
        "annstone",
        "AnnStone",
        "AnnStone",
        "display",
        license="Freeware (Dieter Steffmann)",
        description="Carved, stone-look capitals.",
    ),
)

STYLE_MAP: dict[str, DropcapStyle] = {style.key: style for style in STYLES}


def get_style(key: str | None) -> DropcapStyle | None:
    """Return the style for ``key``, or ``None`` for blank/unknown keys."""
    if not key:
        return None
    return STYLE_MAP.get(key)


def is_style_key(value: str | None) -> bool:
    return bool(value) and value in STYLE_MAP


def parse_class(css_class: str) -> str | None:
    """Map ``dropcap-<key>`` to ``<key>`` when it names a known style."""
    if not css_class.startswith(CLASS_PREFIX):
        return None
    key = css_class[len(CLASS_PREFIX) :]
    return key if key in STYLE_MAP else None


def grouped_styles() -> list[tuple[str, str, list[DropcapStyle]]]:
    """Styles bucketed by group, in registry order."""
    return [
        (group_key, group_label, [s for s in STYLES if s.group == group_key])
        for group_key, group_label in GROUPS
    ]


def _grouped_choices() -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        (group_label, [(s.key, s.label) for s in styles])
        for _, group_label, styles in grouped_styles()
        if styles
    ]


def site_dropcap_choices() -> list:
    """Choices for ``SiteSettings.default_dropcap_style`` (blank = off)."""
    return [(INHERIT, "None (off)")] + _grouped_choices()


def document_dropcap_choices() -> list:
    """Choices for ``Post.dropcap_style`` / ``Page.dropcap_style``."""
    return [
        (INHERIT, "Inherit site default"),
        (NONE, "None (off for this document)"),
    ] + _grouped_choices()


def resolve_style(document_value: str | None, site_value: str | None) -> str:
    """
    The effective style key for a document, or ``""`` when no dropcap
    should show: the document's own choice unless it inherits, in which
    case the site default; ``NONE`` at either level means off.
    """
    if document_value == NONE:
        return ""
    if is_style_key(document_value):
        return document_value  # type: ignore[return-value]
    if is_style_key(site_value):
        return site_value  # type: ignore[return-value]
    return ""


def clamp_lines(value) -> int | None:
    """Parse a ``lines=`` block attribute; ``None`` when unusable."""
    try:
        lines = int(str(value).strip())
    except TypeError, ValueError:
        return None
    if lines < MIN_LINES or lines > MAX_LINES:
        return None
    return lines


def editor_fence_snippets() -> list[dict]:
    """Fenced-div snippets for the editor's ``:::`` completion."""
    return [
        {
            "className": "dropcap-STYLE",
            "detail": "Dropcap in a named style",
            "template": "::: {.dropcap-${1:cinzel}}\n${2:Paragraph}\n:::\n$0",
        },
        {
            "className": "dropcap",
            "detail": "Dropcap in the document's style (lines= 2–6)",
            "template": "::: {.dropcap lines=${1:3}}\n${2:Paragraph}\n:::\n$0",
        },
        {
            "className": "dropcap-not",
            "detail": "No automatic dropcap on this opening paragraph",
            "template": "::: {.dropcap-not}\n${1:Paragraph}\n:::\n$0",
        },
    ]


def editor_inline_classes() -> list[dict]:
    """Class names for the editor's ``{.`` completion: the two switches plus
    one entry per style."""
    entries = [
        {"name": "dropcap", "detail": "Dropcap (document style)"},
        {"name": "dropcap-not", "detail": "Suppress the automatic dropcap"},
    ]
    entries.extend(
        {"name": style.css_class, "detail": f"Dropcap: {style.label}"}
        for style in STYLES
    )
    return entries
