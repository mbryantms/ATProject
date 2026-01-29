"""
API views for presigned upload functionality.

Endpoints:
- POST /api/v1/assets/presigned-upload/ - Request a presigned URL for direct upload
- POST /api/v1/assets/{asset_id}/confirm-upload/ - Confirm upload completion
- DELETE /api/v1/assets/{asset_id}/cancel-upload/ - Cancel and cleanup failed upload
"""

import json
import os

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .auth import api_auth_required
from .presigned import (
    generate_presigned_put_url,
    generate_upload_token,
    get_asset_upload_key,
    verify_object_exists,
)


def get_asset_type_from_extension(filename):
    """Detect asset type from file extension."""
    ext = os.path.splitext(filename)[1].lower()

    image_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"]
    video_exts = [".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"]
    audio_exts = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]
    document_exts = [".pdf", ".epub", ".doc", ".docx", ".txt", ".md"]
    archive_exts = [".zip", ".tar", ".gz", ".bz2", ".7z", ".rar"]

    if ext in image_exts:
        return "image"
    elif ext in video_exts:
        return "video"
    elif ext in audio_exts:
        return "audio"
    elif ext in document_exts:
        return "document"
    elif ext in archive_exts:
        return "archive"
    return "other"


def validate_file_size(file_size, asset_type):
    """
    Validate file size against configured limits.

    Returns (is_valid, error_message)
    """
    max_sizes = getattr(
        settings,
        "ASSET_MAX_SIZES",
        {
            "image": 100 * 1024 * 1024,
            "video": 5 * 1024 * 1024 * 1024,
            "audio": 500 * 1024 * 1024,
            "document": 100 * 1024 * 1024,
            "archive": 1 * 1024 * 1024 * 1024,
            "other": 100 * 1024 * 1024,
        },
    )

    max_size = max_sizes.get(asset_type, 100 * 1024 * 1024)

    if file_size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        return False, f"File size exceeds maximum of {max_size_mb:.0f}MB for {asset_type}"

    return True, None


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def request_presigned_upload(request):
    """
    Request a presigned URL for direct upload to R2.

    POST /api/v1/assets/presigned-upload/

    Request body:
    {
        "filename": "large-video.mp4",
        "content_type": "video/mp4",
        "file_size": 524288000,
        "title": "My Video",
        "alt_text": "",           // optional
        "asset_folder_id": 1,     // optional
        "asset_tags": [1, 2]      // optional
    }

    Response (201):
    {
        "asset_id": 42,
        "upload_url": "https://<account>.r2.cloudflarestorage.com/...",
        "upload_headers": {"Content-Type": "video/mp4"},
        "expires_at": "2024-01-15T12:30:00Z"
    }
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Required fields
    filename = data.get("filename")
    content_type = data.get("content_type")
    file_size = data.get("file_size")
    title = data.get("title")

    if not filename:
        return JsonResponse({"error": "filename is required"}, status=400)
    if not content_type:
        return JsonResponse({"error": "content_type is required"}, status=400)
    if not file_size:
        return JsonResponse({"error": "file_size is required"}, status=400)
    if not title:
        return JsonResponse({"error": "title is required"}, status=400)

    try:
        file_size = int(file_size)
    except (ValueError, TypeError):
        return JsonResponse({"error": "file_size must be an integer"}, status=400)

    # Detect asset type from filename
    asset_type = get_asset_type_from_extension(filename)

    # Validate file size
    is_valid, error = validate_file_size(file_size, asset_type)
    if not is_valid:
        return JsonResponse({"error": error}, status=400)

    # Optional fields
    alt_text = data.get("alt_text", "")
    asset_folder_id = data.get("asset_folder_id")
    asset_tag_ids = data.get("asset_tags", [])

    # Generate the object key for R2
    object_key = get_asset_upload_key(filename, asset_type)

    # Generate presigned URL
    upload_url, expires_at = generate_presigned_put_url(object_key, content_type)

    # Generate upload token
    upload_token = generate_upload_token()

    # Create placeholder Asset record
    from engine.models import Asset, AssetFolder

    asset = Asset(
        title=title,
        asset_type=asset_type,
        original_filename=filename,
        file_extension=os.path.splitext(filename)[1].lstrip(".").lower(),
        mime_type=content_type,
        file_size=file_size,
        alt_text=alt_text,
        status="uploading",
        uploaded_by=request.api_user,
        upload_token=upload_token,
        upload_expires_at=expires_at,
    )

    # Set the file field to point to the expected R2 location
    # This is set after upload confirmation
    asset.file.name = object_key

    # Handle optional folder
    if asset_folder_id:
        try:
            asset.asset_folder = AssetFolder.objects.get(pk=asset_folder_id)
        except AssetFolder.DoesNotExist:
            return JsonResponse({"error": "asset_folder_id not found"}, status=400)

    asset.save()

    # Handle optional tags (M2M relationship, must be after save)
    if asset_tag_ids:
        from engine.models import AssetTag

        tags = AssetTag.objects.filter(pk__in=asset_tag_ids)
        asset.asset_tags.set(tags)

    return JsonResponse(
        {
            "asset_id": asset.pk,
            "upload_url": upload_url,
            "upload_headers": {"Content-Type": content_type},
            "expires_at": expires_at.isoformat(),
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def confirm_upload(request, asset_id):
    """
    Confirm that a presigned upload has completed.

    POST /api/v1/assets/{asset_id}/confirm-upload/

    Response (200):
    {
        "asset_id": 42,
        "status": "processing",
        "processing_task_id": "celery-task-id"
    }
    """
    from engine.models import Asset

    try:
        asset = Asset.all_objects.get(pk=asset_id)
    except Asset.DoesNotExist:
        return JsonResponse({"error": "Asset not found"}, status=404)

    # Verify ownership (must be uploader or superuser)
    if not request.api_user.is_superuser and asset.uploaded_by != request.api_user:
        return JsonResponse({"error": "Not authorized"}, status=403)

    # Check asset is in uploading state
    if asset.status != "uploading":
        return JsonResponse(
            {"error": f"Asset is not in uploading state (current: {asset.status})"},
            status=400,
        )

    # Check upload hasn't expired
    if asset.upload_expires_at and timezone.now() > asset.upload_expires_at:
        return JsonResponse({"error": "Upload has expired"}, status=400)

    # Verify file exists in R2
    object_key = asset.file.name
    result = verify_object_exists(object_key)

    if not result["exists"]:
        return JsonResponse(
            {"error": "File not found in storage. Upload may have failed."},
            status=400,
        )

    # Update file size from actual upload (may differ from initial estimate)
    if result.get("size"):
        asset.file_size = result["size"]

    # Update status to processing
    asset.status = "processing"
    asset.upload_token = None  # Clear single-use token
    asset.save(update_fields=["status", "upload_token", "file_size"])

    # Queue processing task
    task_id = None
    try:
        from engine.tasks import finalize_presigned_upload

        task = finalize_presigned_upload.delay(asset.pk)
        task_id = task.id
    except Exception as e:
        # If Celery is unavailable, process synchronously
        from engine.tasks import finalize_presigned_upload

        finalize_presigned_upload(asset.pk)

    return JsonResponse(
        {
            "asset_id": asset.pk,
            "status": "processing",
            "processing_task_id": task_id,
        },
        status=200,
    )


@csrf_exempt
@require_http_methods(["DELETE"])
@api_auth_required
def cancel_upload(request, asset_id):
    """
    Cancel a presigned upload and delete the placeholder Asset.

    DELETE /api/v1/assets/{asset_id}/cancel-upload/

    Response (200):
    {
        "success": true,
        "message": "Upload cancelled"
    }
    """
    from engine.models import Asset

    try:
        asset = Asset.all_objects.get(pk=asset_id)
    except Asset.DoesNotExist:
        return JsonResponse({"error": "Asset not found"}, status=404)

    # Verify ownership (must be uploader or superuser)
    if not request.api_user.is_superuser and asset.uploaded_by != request.api_user:
        return JsonResponse({"error": "Not authorized"}, status=403)

    # Only allow cancellation of assets in uploading state
    if asset.status != "uploading":
        return JsonResponse(
            {"error": f"Cannot cancel asset in {asset.status} state"},
            status=400,
        )

    # Delete the placeholder asset (hard delete since it was never completed)
    asset.delete()

    # Note: We don't attempt to delete the partial file from R2
    # - It may not exist yet
    # - R2 lifecycle rules should handle cleanup of orphaned files

    return JsonResponse(
        {
            "success": True,
            "message": "Upload cancelled",
        },
        status=200,
    )
