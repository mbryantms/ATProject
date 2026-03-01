"""
Gunicorn configuration for ATProject.

Ensures clean database connection state across worker lifecycle events,
which is critical for letting Neon serverless Postgres scale to zero.
"""

import os

# ---------------------------------------------------------------------------
# Server socket
# ---------------------------------------------------------------------------
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------
# Recycle workers after N requests to prevent resource leaks.
max_requests = 1000
max_requests_jitter = 50

# ---------------------------------------------------------------------------
# Worker lifecycle hooks
# ---------------------------------------------------------------------------


def post_fork(server, worker):
    """
    Close all Django DB connections immediately after a worker forks.

    The forked worker inherits the master's file descriptors, including any
    open Postgres connections (e.g. from running ``migrate`` in the Dockerfile
    CMD before starting Gunicorn).  Those inherited connections are in an
    undefined state and will hold Neon's compute open.  Closing them here
    forces each worker to establish its own connection on the first request,
    which Django then closes per CONN_MAX_AGE=0.
    """
    import django
    from django.conf import settings

    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ATProject.settings")
        django.setup()

    from django import db

    db.connections.close_all()


def pre_request(worker, req):
    """
    Close stale connections before each request.

    With CONN_MAX_AGE=0 Django already calls close_old_connections() around
    each request, but this belt-and-suspenders hook ensures no leaked
    connection survives between requests — important for Neon auto-suspend.
    """
    from django import db

    db.close_old_connections()
