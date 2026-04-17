"""
Tests for API authentication decorator.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from engine.api.auth import api_auth_required

User = get_user_model()


@api_auth_required
def dummy_view(request):
    from django.http import JsonResponse

    return JsonResponse({"user": request.api_user.username})


class ApiAuthTests(TestCase):
    """Test the @api_auth_required decorator."""

    def setUp(self):
        self.factory = RequestFactory()
        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="testpass123",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="admin",
            password="adminpass123",
        )
        self.regular_user = User.objects.create_user(
            username="regular",
            password="testpass123",
            is_staff=False,
        )

    def test_no_auth_returns_401(self):
        request = self.factory.get("/api/test/")
        request.user = self._anonymous_user()
        response = dummy_view(request)
        self.assertEqual(response.status_code, 401)

    def test_invalid_bearer_token_returns_401(self):
        request = self.factory.get(
            "/api/test/", HTTP_AUTHORIZATION="Bearer wrong-token"
        )
        request.user = self._anonymous_user()
        response = dummy_view(request)
        self.assertEqual(response.status_code, 401)

    def test_valid_bearer_token_succeeds(self):
        with self.settings(PRESIGNED_UPLOAD_API_TOKEN="test-secret-token"):
            request = self.factory.get(
                "/api/test/",
                HTTP_AUTHORIZATION="Bearer test-secret-token",
            )
            request.user = self._anonymous_user()
            response = dummy_view(request)
            self.assertEqual(response.status_code, 200)

    def test_bearer_token_without_configured_token_returns_401(self):
        """If PRESIGNED_UPLOAD_API_TOKEN is not set, bearer auth should fail."""
        with self.settings(PRESIGNED_UPLOAD_API_TOKEN=None):
            request = self.factory.get(
                "/api/test/",
                HTTP_AUTHORIZATION="Bearer any-token",
            )
            request.user = self._anonymous_user()
            response = dummy_view(request)
            self.assertEqual(response.status_code, 401)

    def test_non_staff_session_user_returns_403(self):
        request = self.factory.get("/api/test/")
        request.user = self.regular_user
        # Skip CSRF for this test (session auth requires CSRF)
        request.META["HTTP_X_CSRFTOKEN"] = "dummy"
        response = dummy_view(request)
        # Non-staff users get 403
        self.assertEqual(response.status_code, 403)

    def _anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser

        return AnonymousUser()
