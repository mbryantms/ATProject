import math

from django import template

register = template.Library()


def _clamp_int(value, lo=1, hi=10) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def _color_for_scheme(pct: float, scheme: str) -> str:
    """
    Return a color for the gauge. pct = 0.0..1.0
    - 'certainty': red→green across 0..120 hue
    - 'importance': amber-ish ramp (fixed hue, vary lightness)
    - 'mono': use currentColor (lets surrounding text color control it)
    """
    scheme = (scheme or "certainty").lower()
    if scheme == "mono":
        # handled in SVG by using 'currentColor'
        return "currentColor"
    if scheme == "importance":
        # Amber ramp: fixed hue ~38, vary lightness by pct
        light = 35 + int(25 * pct)  # 35%..60%
        return f"hsl(38 85% {light}%)"
    # default: certainty red→green
    hue = int(120 * pct)  # 0=red, 120=green
    return f"hsl({hue} 70% 45%)"


@register.inclusion_tag("components/gauge.svg")
def gauge(
    value: int,
    size: int = 24,
    label: str | None = None,
    scheme: str = "certainty",
    max_value: int = 10,
    show_number: bool = True,
):
    """
    Generic circular gauge (1..max_value). Defaults to certainty-style coloring.
    Usage examples:
      {% gauge post.certainty 24 "Certainty" "certainty" %}
      {% gauge post.importance 24 "Importance" "importance" %}
      {% gauge post.certainty 20 "Certainty" "mono" %}
    """
    v = _clamp_int(value, lo=1, hi=max_value)
    pct = max(0.0, min(1.0, v / float(max_value)))
    r = 9.0
    c = 2 * math.pi * r
    progress = c * pct
    gap = c - progress
    color = _color_for_scheme(pct, scheme)
    aria = label or f"Value {v} out of {max_value} ({int(pct*100)}%)"

    return {
        "v": v,
        "max_value": max_value,
        "pct": int(pct * 100),
        "size": int(size),
        "c": c,
        "progress": progress,
        "gap": gap,
        "color": color,
        "use_current_color": (scheme.lower() == "mono"),
        "aria": aria,
        "show_number": bool(show_number),
    }
