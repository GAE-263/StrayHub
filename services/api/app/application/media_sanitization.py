from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from services.api.app.api.errors import DomainError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_MIME_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def sanitize_image(data: bytes, *, declared_content_type: str) -> tuple[bytes, str, str]:
    if len(data) > MAX_IMAGE_BYTES:
        raise DomainError("media_too_large", "照片超過允許大小", 422)
    image_format = SUPPORTED_MIME_TYPES.get(declared_content_type)
    if image_format is None:
        raise DomainError("unsupported_media_type", "照片格式不受支援", 422)
    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            actual_format = (source.format or "").upper()
            if actual_format != image_format:
                raise DomainError("invalid_media_format", "照片實際格式與宣告不一致", 422)
            rgb_image = source.convert("RGB") if image_format == "JPEG" else source.copy()
            output = BytesIO()
            save_format = "JPEG" if image_format == "JPEG" else image_format
            rgb_image.save(output, format=save_format)
            cleaned = output.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise DomainError("invalid_image", "照片無法解碼", 422) from exc

    checksum = hashlib.sha256(cleaned).hexdigest()
    return cleaned, declared_content_type, checksum
