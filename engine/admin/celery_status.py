"""
Live Celery worker / task visibility for the Django admin.

The result backend in this project is Redis (not ``django-db``) so no
``TaskResult`` rows are ever written and the default admin page is empty.
This module adds an admin-side page at ``<admin>/celery-status/`` that
calls ``celery.current_app.control.inspect()`` to show what's happening
right now: which workers are connected, what they're running, what's
queued, and recent failures/stats. All data is read from Redis/broker —
nothing new is written to the database.

The page also exposes a small helper ``active_tasks_for_asset(asset)``
used by ``AssetAdmin.processing_state`` to annotate each asset with the
tasks currently running against it.
"""

from __future__ import annotations

import json
import time
from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from django.shortcuts import render
from django.urls import path
from django.utils.timezone import now

# How long (seconds) to wait for workers to respond to an inspect() ping.
# Redis ping is fast; keep this tight so the admin page never hangs the UI
# if workers are down.
_INSPECT_TIMEOUT = 2.0

# Small in-process cache for inspect() results so multiple admin widgets
# on the same page don't hammer the broker. Cached per-process; workers
# refresh roughly twice a second in practice, so 3s is a reasonable TTL.
_CACHE_TTL = 3.0
_cache: dict[str, tuple[float, Any]] = {}


def _cached_inspect(method: str):
    """Return inspect().<method>() with a tiny in-process cache."""
    from celery import current_app

    key = f"inspect:{method}"
    now_ts = time.monotonic()
    cached = _cache.get(key)
    if cached and (now_ts - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        inspector = current_app.control.inspect(timeout=_INSPECT_TIMEOUT)
        value = getattr(inspector, method)() or {}
    except Exception as exc:  # broker down, Redis unreachable, etc.
        value = {"__error__": str(exc)}

    _cache[key] = (now_ts, value)
    return value


def _humanize_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = float(seconds)
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"


def _short_task_name(name: str | None) -> str:
    if not name:
        return ""
    return name.rsplit(".", 1)[-1]


def _normalize_task_args(raw_args) -> str:
    """Best-effort rendering of Celery-reported args for admin display."""
    try:
        if isinstance(raw_args, str):
            return raw_args
        return json.dumps(raw_args, default=str)
    except Exception:
        return repr(raw_args)


def _collect_active_tasks() -> list[dict]:
    """Return active tasks across all workers, flattened with runtime."""
    active_by_worker = _cached_inspect("active")
    if not isinstance(active_by_worker, dict) or "__error__" in active_by_worker:
        return []

    rows = []
    now_epoch = time.time()
    for worker, tasks in active_by_worker.items():
        for task in tasks or []:
            time_start = task.get("time_start")
            runtime = (now_epoch - time_start) if time_start else None
            rows.append(
                {
                    "worker": worker,
                    "task_id": task.get("id", ""),
                    "task_name": task.get("name", ""),
                    "task_short_name": _short_task_name(task.get("name")),
                    "args": _normalize_task_args(task.get("args")),
                    "kwargs": _normalize_task_args(task.get("kwargs")),
                    "runtime_seconds": runtime,
                    "runtime_human": _humanize_duration(runtime),
                }
            )
    rows.sort(key=lambda r: -(r["runtime_seconds"] or 0))
    return rows


def _collect_reserved_tasks() -> list[dict]:
    """Return tasks queued per-worker but not yet running."""
    reserved = _cached_inspect("reserved")
    if not isinstance(reserved, dict) or "__error__" in reserved:
        return []

    rows = []
    for worker, tasks in reserved.items():
        for task in tasks or []:
            rows.append(
                {
                    "worker": worker,
                    "task_id": task.get("id", ""),
                    "task_name": task.get("name", ""),
                    "task_short_name": _short_task_name(task.get("name")),
                    "args": _normalize_task_args(task.get("args")),
                    "kwargs": _normalize_task_args(task.get("kwargs")),
                }
            )
    return rows


def _collect_worker_stats() -> list[dict]:
    """Return per-worker pool / processed / load stats."""
    stats = _cached_inspect("stats")
    if not isinstance(stats, dict) or "__error__" in stats:
        return []

    rows = []
    for worker, data in stats.items():
        if not isinstance(data, dict):
            continue
        pool = data.get("pool", {}) or {}
        total = data.get("total", {}) or {}
        rusage = data.get("rusage", {}) or {}
        rows.append(
            {
                "worker": worker,
                "pool_impl": pool.get("implementation", ""),
                "pool_size": pool.get("max-concurrency") or pool.get("processes"),
                "load_avg": data.get("load_avg") or data.get("loadavg") or [],
                "total_tasks": sum(total.values()) if isinstance(total, dict) else 0,
                "by_task": total if isinstance(total, dict) else {},
                "uptime": data.get("uptime"),
                "rusage_user": rusage.get("utime"),
                "rusage_sys": rusage.get("stime"),
            }
        )
    rows.sort(key=lambda r: r["worker"])
    return rows


def _broker_error() -> str | None:
    """If inspect() failed globally, surface a single explanation."""
    stats = _cache.get("inspect:stats")
    active = _cache.get("inspect:active")
    for cached in (stats, active):
        if cached and isinstance(cached[1], dict) and "__error__" in cached[1]:
            return cached[1]["__error__"]
    return None


def active_tasks_for_asset(asset) -> list[dict]:
    """Return currently-running tasks whose args reference ``asset``.

    Used by AssetAdmin.processing_state to show 'this asset is being
    transcoded right now by worker X'. Called per admin detail view, so
    it piggybacks on the cache above (no extra broker round-trip when
    multiple widgets hit it in the same request).
    """
    if not asset or not asset.pk:
        return []

    pk_str = str(asset.pk)
    key = asset.key or ""
    matches = []
    for task in _collect_active_tasks():
        blob = f"{task['args']} {task['kwargs']}"
        if pk_str and (
            f"[{pk_str}]" in blob
            or f", {pk_str}" in blob
            or f"({pk_str}" in blob
            or f" {pk_str}," in blob
        ):
            matches.append(task)
        elif key and key in blob:
            matches.append(task)
    return matches


# ---------------------------------------------------------------------------
# Admin view
# ---------------------------------------------------------------------------


def celery_status_view(request: HttpRequest):
    """Render a read-only dashboard of live Celery state."""
    # Bust the cache on explicit refresh so the "Refresh" button shows
    # the current truth.
    if request.GET.get("refresh"):
        _cache.clear()

    context = {
        **admin.site.each_context(request),
        "title": "Celery status",
        "now": now(),
        "workers": _collect_worker_stats(),
        "active_tasks": _collect_active_tasks(),
        "reserved_tasks": _collect_reserved_tasks(),
        "broker_error": _broker_error(),
    }
    return render(request, "admin/celery_status.html", context)


# ---------------------------------------------------------------------------
# URL injection — append the view to admin.site.get_urls() at resolve time
# ---------------------------------------------------------------------------


def _install_urls_once() -> None:
    """Idempotently inject ``celery-status/`` into the admin URL tree.

    Wrapping ``admin.site.get_urls`` this way keeps the view accessible
    under the admin namespace (``admin:celery_status``) without forcing
    the project to adopt a custom ``AdminSite`` subclass.
    """
    if getattr(admin.site, "_celery_status_installed", False):
        return

    original_get_urls = admin.site.get_urls

    def patched_get_urls():
        custom = [
            path(
                "celery-status/",
                admin.site.admin_view(celery_status_view),
                name="celery_status",
            ),
        ]
        return custom + original_get_urls()

    admin.site.get_urls = patched_get_urls
    admin.site._celery_status_installed = True


_install_urls_once()
