"""Shared admin display helpers.

Centralizes the small HTML-rendering patterns that were previously duplicated
(and, in taxonomy.py, hand-rolled with hardcoded hex colors) across the admin:

- ``mk_pill`` renders a status badge with the shared ``.mk-pill`` classes from
  ``static/css/admin-common.css``. Those classes are built on Django admin CSS
  variables, so they adapt to light/dark automatically — unlike inline hex.
- ``admin_change_link`` / ``admin_changelist_link`` build links via
  ``reverse()`` under the ``admin:`` namespace, so they keep working when the
  admin is mounted somewhere other than ``/admin/`` (this project mounts it at
  ``/manage/`` via ``ADMIN_URL``, which broke the old hardcoded ``/admin/…``
  links).

Everything goes through ``format_html`` so values are always escaped.
"""

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.html import format_html

#: Allowed pill tones (mirror the .mk-pill--* classes in admin-common.css).
PILL_TONES = frozenset({"success", "warn", "danger", "info", "muted"})


def mk_pill(label, tone="muted", *, size=None):
    """Render a status pill using the shared ``.mk-pill`` classes.

    ``tone`` is one of ``success|warn|danger|info|muted``. ``size`` is an
    optional ``sm|lg`` modifier. Falls back to the neutral ``muted`` tone for
    unknown values so a bad status string never produces broken markup.
    """
    if tone not in PILL_TONES:
        tone = "muted"
    classes = f"mk-pill mk-pill--{tone}"
    if size in {"sm", "lg"}:
        classes += f" mk-pill--{size}"
    return format_html('<span class="{}">{}</span>', classes, label)


def admin_change_link(obj, label=None):
    """Return an ``<a>`` to an object's admin change page (namespace-safe)."""
    if obj is None or obj.pk is None:
        return ""
    meta = obj._meta
    url = reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[obj.pk])
    return format_html(
        '<a href="{}">{}</a>', url, label if label is not None else str(obj)
    )


def admin_changelist_link(model, label, **query):
    """Return an ``<a>`` to a model's admin changelist, with optional filters.

    Example: ``admin_changelist_link(Post, "3 posts", tags__id__exact=tag.pk)``.
    """
    meta = model._meta
    url = reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")
    if query:
        url = f"{url}?{urlencode(query)}"
    return format_html('<a href="{}">{}</a>', url, label)


def muted(text="—"):
    """Render dimmed placeholder text using the shared ``.mk-muted`` class."""
    return format_html('<span class="mk-muted">{}</span>', text)
