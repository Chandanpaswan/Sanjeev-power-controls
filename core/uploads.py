"""Validated upload helpers shared by dashboard forms."""
from __future__ import annotations

from pathlib import Path

from django import forms
from django.conf import settings

IMAGE_MAX_BYTES = getattr(settings, "IMAGE_MAX_BYTES", 3 * 1024 * 1024)
MEDIA_MAX_BYTES = getattr(settings, "MEDIA_MAX_BYTES", 5 * 1024 * 1024)
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DOCUMENT_CONTENT_TYPES = {"application/pdf"}
DOCUMENT_EXTENSIONS = {".pdf"}
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".dll", ".js", ".mjs", ".html",
    ".htm", ".php", ".py", ".sh", ".ps1", ".svg", ".xml", ".zip", ".rar",
}


def validate_image_upload(upload, max_bytes=None):
    """Validate a Django UploadedFile and return it, reset to position 0."""
    if not upload:
        return upload
    max_bytes = max_bytes or IMAGE_MAX_BYTES
    if getattr(upload, "size", 0) > max_bytes:
        raise forms.ValidationError(f"The image must be {max_bytes // (1024 * 1024)} MB or smaller.")
    suffix = Path(getattr(upload, "name", "")).suffix.lower()
    if suffix in BLOCKED_EXTENSIONS or suffix not in IMAGE_EXTENSIONS:
        raise forms.ValidationError("Upload a JPG, PNG, WebP or GIF image.")
    content_type = getattr(upload, "content_type", "")
    if content_type and content_type not in IMAGE_CONTENT_TYPES:
        raise forms.ValidationError("The uploaded file is not a supported image type.")
    try:
        from PIL import Image

        upload.seek(0)
        with Image.open(upload) as probe:
            width, height = probe.size
            if width * height > 40_000_000:
                raise forms.ValidationError("The image dimensions are too large (maximum 40 megapixels).")
            probe.verify()
        upload.seek(0)
    except forms.ValidationError:
        raise
    except Exception:
        raise forms.ValidationError("The uploaded file is not a valid image.")
    return upload


def validate_media_upload(upload):
    if not upload:
        return upload
    if getattr(upload, "size", 0) > MEDIA_MAX_BYTES:
        raise forms.ValidationError("Files must be 5 MB or smaller.")
    suffix = Path(getattr(upload, "name", "")).suffix.lower()
    content_type = getattr(upload, "content_type", "")
    if suffix in BLOCKED_EXTENSIONS:
        raise forms.ValidationError("This file type is not permitted.")
    if suffix in IMAGE_EXTENSIONS:
        validate_image_upload(upload, max_bytes=MEDIA_MAX_BYTES)
    elif suffix in DOCUMENT_EXTENSIONS and content_type in ("application/pdf", "application/octet-stream", ""):
        upload.seek(0)
        header = upload.read(5)
        upload.seek(0)
        if header != b"%PDF-":
            raise forms.ValidationError("The uploaded PDF is not valid.")
    else:
        raise forms.ValidationError("Upload a JPG, PNG, WebP, GIF image or a PDF document.")
    return upload


def image_asset_queryset():
    from cms.models import MediaAsset

    return MediaAsset.objects.filter(file_type=MediaAsset.TYPE_IMAGE).order_by("-created_at")
