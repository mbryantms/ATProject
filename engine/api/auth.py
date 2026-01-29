"""
Authentication utilities for the presigned upload API.

Provides @api_auth_required decorator supporting:
- Django session auth (for admin UI)
- Bearer token auth (for programmatic access)
- Requires is_staff permission
"""

from functools import wraps

from django.conf import settings
from django.http import JsonResponse


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

        # Method 1: Check Django session authentication
        if request.user.is_authenticated:
            user = request.user

        # Method 2: Check Bearer token authentication
        if user is None:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Strip "Bearer " prefix
                api_token = getattr(settings, "PRESIGNED_UPLOAD_API_TOKEN", None)

                if api_token and token == api_token:
                    # Token auth doesn't have a user object, but we need to
                    # create a minimal user-like object for the view
                    from django.contrib.auth import get_user_model

                    User = get_user_model()
                    # For token auth, we use the first superuser as the authenticated user
                    # This ensures proper ownership tracking
                    user = User.objects.filter(is_superuser=True).first()
                    if user is None:
                        user = User.objects.filter(is_staff=True).first()

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

    return wrapper
