from __future__ import annotations

ALLOWED_MEDICAL_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


def media_type_allowed(content_type: str) -> bool:
    return content_type.lower().strip() in ALLOWED_MEDICAL_MEDIA_TYPES
