"""Template filter for icon-field values (see engine.icons)."""

from django import template

from engine.icons import icon_html

register = template.Library()


@register.filter(name="tag_icon")
def tag_icon(value):
    """Render an icon-field value: inline Lucide SVG or escaped literal."""
    return icon_html(value)
