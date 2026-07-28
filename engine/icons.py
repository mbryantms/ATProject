"""
Lucide icon support for icon fields (Tag.icon).

Icon-field values stay free text: a literal glyph/emoji renders as-is,
while ``lucide:<name>`` renders the named icon from the vendored sprite
(static/img/lucide/sprite.svg, refresh with ``npm run icons:update``) as an
inline SVG. Inlining means public pages never fetch the ~480K sprite, and
``stroke="currentColor"`` makes the icon follow the surrounding text color
in both themes. The admin picker, which shows every icon at once, uses
``<use>`` references against the sprite instead — one cacheable fetch there.
"""

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import SafeString, mark_safe

LUCIDE_PREFIX = "lucide:"
SPRITE_STATIC_PATH = "img/lucide/sprite.svg"


def _sprite_file() -> Path | None:
    found = finders.find(SPRITE_STATIC_PATH)
    if found:
        return Path(found)
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        candidate = Path(static_root) / SPRITE_STATIC_PATH
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def _sprite_text() -> str:
    path = _sprite_file()
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def lucide_icon_names() -> tuple[str, ...]:
    """All icon names available in the vendored sprite, in sprite order."""
    return tuple(re.findall(r'<symbol[^>]*\bid="([a-z0-9-]+)"', _sprite_text()))


@lru_cache(maxsize=1024)
def _symbol_inner(name: str) -> str | None:
    """The path markup inside one sprite symbol (no wrapper element)."""
    match = re.search(
        rf'<symbol[^>]*\bid="{re.escape(name)}"[^>]*>(.*?)</symbol>',
        _sprite_text(),
        re.DOTALL,
    )
    return match.group(1) if match else None


def icon_html(value: str | None) -> SafeString | str:
    """Render an icon-field value for templates and admin displays.

    ``lucide:<name>`` becomes a self-contained inline SVG (sized and
    baseline-aligned via its own attributes, so no CSS is required at the
    call site); anything else is escaped and rendered literally. Unknown
    lucide names render as nothing rather than leaking the raw identifier.
    """
    if not value:
        return ""
    value = value.strip()
    if not value.startswith(LUCIDE_PREFIX):
        return conditional_escape(value)
    inner = _symbol_inner(value[len(LUCIDE_PREFIX) :])
    if inner is None:
        return ""
    return format_html(
        '<svg class="lucide-icon" viewBox="0 0 24 24" width="1em" height="1em" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        'style="vertical-align:-0.125em">{}</svg>',
        mark_safe(inner),  # vendored sprite content, not user input
    )
