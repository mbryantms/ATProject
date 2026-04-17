"""
Authentication utilities for the presigned upload API.

Provides @api_auth_required decorator supporting:
- Django session auth (for admin UI)
- Bearer token auth (for programmatic access)
- Requires is_staff permission
"""

import hmac
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware


def api_auth_required(view_func):
    """
    Decorator that requires authentication via session or Bearer token.

    Supports two authentication methods:
    1. Django session authentication (for browser/admin use)
    2. Bearer token authentication (for programmatic access)

    Both methods require the user to have is_staff=True.

    Usage:
        @api_auth_required
        def my_view(request):
            # request.user is guaranteed to be authenticated staff
            pass
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = None
        is_bearer = False

        # Method 1: Check Bearer token authentication first
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            is_bearer = True
            token = auth_header[7:]  # Strip "Bearer " prefix
            api_token = getattr(settings, "PRESIGNED_UPLOAD_API_TOKEN", None)

            if not api_token or not hmac.compare_digest(token, api_token):
                return JsonResponse(
                    {"error": "Invalid API token"},
                    status=401,
                )

            from django.contrib.auth import get_user_model

            User = get_user_model()
            # Use the designated API user (first superuser, then first staff).
            # Fail explicitly if no suitable user exists.
            user = User.objects.filter(is_superuser=True).first()
            if user is None:
                user = User.objects.filter(is_staff=True).first()
            if user is None:
                return JsonResponse(
                    {"error": "No staff user configured for API access"},
                    status=500,
                )

        # Method 2: Check Django session authentication
        if user is None and not is_bearer and request.user.is_authenticated:
            # Verify CSRF for session-authenticated requests
            csrf_middleware = CsrfViewMiddleware(lambda req: None)
            csrf_result = csrf_middleware.process_view(request, view_func, args, kwargs)
            if csrf_result is not None:
                return JsonResponse(
                    {"error": "CSRF verification failed"},
                    status=403,
                )
            user = request.user

        # Check authentication
        if user is None:
            return JsonResponse(
                {"error": "Authentication required"},
                status=401,
            )

        # Check staff permission
        if not user.is_staff:
            return JsonResponse(
                {"error": "Staff permission required"},
                status=403,
            )

        # Attach user to request for views that need it
        request.api_user = user

        return view_func(request, *args, **kwargs)

    # Mark as csrf_exempt so middleware skips it; we handle CSRF manually above
    wrapper.csrf_exempt = True
    return wrapper
