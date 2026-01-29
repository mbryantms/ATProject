"""
URL patterns for the presigned upload API.

Endpoints:
- POST /api/v1/assets/presigned-upload/ - Request presigned URL
- POST /api/v1/assets/<id>/confirm-upload/ - Confirm upload complete
- DELETE /api/v1/assets/<id>/cancel-upload/ - Cancel upload
"""

from django.urls import path

from .views import cancel_upload, confirm_upload, request_presigned_upload

app_name = "api"

urlpatterns = [
    path(
        "v1/assets/presigned-upload/",
        request_presigned_upload,
        name="presigned-upload",
    ),
    path(
        "v1/assets/<int:asset_id>/confirm-upload/",
        confirm_upload,
        name="confirm-upload",
    ),
    path(
        "v1/assets/<int:asset_id>/cancel-upload/",
        cancel_upload,
        name="cancel-upload",
    ),
]
