"""
Boto3 utilities for generating presigned URLs for direct R2/S3 uploads.

This module provides:
- get_s3_client(): Get a configured boto3 S3 client for R2
- generate_presigned_put_url(): Generate a signed PUT URL for direct uploads
- verify_object_exists(): Check if an object exists in R2 via HEAD request
- generate_upload_token(): Generate a secure random token for upload verification
"""

import secrets
from datetime import datetime, timedelta

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.utils import timezone


def get_s3_client():
    """
    Get a boto3 S3 client configured for Cloudflare R2.

    Returns:
        boto3 S3 client configured with R2 credentials and endpoint
    """
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(
            signature_version=settings.AWS_S3_SIGNATURE_VERSION,
            s3={"addressing_style": settings.AWS_S3_ADDRESSING_STYLE},
        ),
    )


def generate_presigned_put_url(key, content_type, expiry_seconds=None):
    """
    Generate a presigned PUT URL for direct file upload to R2.

    Args:
        key: The object key (path) in the bucket
        content_type: The Content-Type of the file being uploaded
        expiry_seconds: URL expiry time in seconds (default: from settings)

    Returns:
        tuple: (presigned_url, expires_at_datetime)
    """
    if expiry_seconds is None:
        expiry_seconds = getattr(settings, "PRESIGNED_UPLOAD_EXPIRY_SECONDS", 3600)

    client = get_s3_client()

    url = client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expiry_seconds,
    )

    expires_at = timezone.now() + timedelta(seconds=expiry_seconds)

    return url, expires_at


def verify_object_exists(key):
    """
    Verify that an object exists in R2 using a HEAD request.

    Args:
        key: The object key (path) in the bucket

    Returns:
        dict with 'exists' (bool) and 'size' (int, if exists) or None
    """
    client = get_s3_client()

    try:
        response = client.head_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
        )
        return {
            "exists": True,
            "size": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "etag": response.get("ETag"),
        }
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return {"exists": False}
        # Re-raise other errors
        raise


def generate_upload_token():
    """
    Generate a secure random token for upload verification.

    Returns:
        str: 64-character hex token (32 bytes of randomness)
    """
    return secrets.token_hex(32)


def get_asset_upload_key(filename, asset_type):
    """
    Generate the object key for a presigned upload.

    Uses the same path structure as Django's FileField upload_to.

    Args:
        filename: Original filename
        asset_type: The asset type (image, video, etc.)

    Returns:
        str: The object key path
    """
    now = timezone.now()
    return f"assets/{now.year}/{now.month:02d}/{filename}"
