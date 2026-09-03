from __future__ import annotations

import hashlib
import warnings
from io import BytesIO
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from services.api.app.api.errors import DomainError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_FINAL_IMAGE_BYTES = 2 * 1024 * 1024
MAX_GROWTH_DIARY_PIXELS = 25_000_000
SUPPORTED_MIME_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
ImageOutputPolicy = Literal["preserve", "growth_diary_webp"]


def _resize_no_upscale(image: Image.Image, *, max_long_edge: int) -> Image.Image:
    resized = image.copy()
    if max(resized.size) > max_long_edge:
        resized.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
    return resized


def _encode_webp(image: Image.Image, *, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="WEBP", quality=quality)
    return output.getvalue()


def _growth_diary_webp(source: Image.Image) -> bytes:
    source.seek(0)
    oriented = ImageOps.exif_transpose(source).copy()
    has_alpha = oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info
    normalized = oriented.convert("RGBA" if has_alpha else "RGB")

    for max_long_edge, quality in ((1600, 82), (1600, 72), (1280, 68)):
        candidate = _resize_no_upscale(normalized, max_long_edge=max_long_edge)
        encoded = _encode_webp(candidate, quality=quality)
        if len(encoded) <= MAX_FINAL_IMAGE_BYTES:
            return encoded

    raise DomainError("media_too_large_after_normalization", "照片壓縮後仍超過允許大小", 422)


def sanitize_image(
    data: bytes,
    *,
    declared_content_type: str,
    output_policy: ImageOutputPolicy = "preserve",
) -> tuple[bytes, str, str]:
    if len(data) > MAX_IMAGE_BYTES:
        raise DomainError("media_too_large", "照片超過允許大小", 422)
    image_format = SUPPORTED_MIME_TYPES.get(declared_content_type)
    if image_format is None:
        raise DomainError("unsupported_media_type", "照片格式不受支援", 422)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                actual_format = (source.format or "").upper()
                if actual_format != image_format:
                    raise DomainError("invalid_media_format", "照片實際格式與宣告不一致", 422)
                width, height = source.size
                if (
                    output_policy == "growth_diary_webp"
                    and width * height > MAX_GROWTH_DIARY_PIXELS
                ):
                    raise DomainError("image_pixel_limit_exceeded", "照片解析度超過允許上限", 422)
                source.load()
                if output_policy == "growth_diary_webp":
                    cleaned = _growth_diary_webp(source)
                    cleaned_content_type = "image/webp"
                else:
                    rgb_image = source.convert("RGB") if image_format == "JPEG" else source.copy()
                    output = BytesIO()
                    save_format = "JPEG" if image_format == "JPEG" else image_format
                    rgb_image.save(output, format=save_format)
                    cleaned = output.getvalue()
                    cleaned_content_type = declared_content_type
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise DomainError("image_pixel_limit_exceeded", "照片解析度超過允許上限", 422) from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise DomainError("invalid_image", "照片無法解碼", 422) from exc

    checksum = hashlib.sha256(cleaned).hexdigest()
    return cleaned, cleaned_content_type, checksum
