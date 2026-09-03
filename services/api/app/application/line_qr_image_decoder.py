from __future__ import annotations

from io import BytesIO

import zxingcpp
from PIL import Image, UnidentifiedImageError

from services.api.app.api.errors import DomainError

_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_IMAGE_PIXELS = 25_000_000
_MAX_QR_TEXT_LENGTH = 2048


def decode_qr_image(content: bytes) -> str:
    """Decode one QR locator from a LINE image without assigning tenant context."""
    if not content or len(content) > _MAX_IMAGE_BYTES:
        raise DomainError("invalid_qr_image", "QR 圖片無效或檔案過大", 422)
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > _MAX_IMAGE_PIXELS:
                raise DomainError("invalid_qr_image", "QR 圖片尺寸過大", 422)
            image.load()
            results = zxingcpp.read_barcodes(
                image,
                formats=zxingcpp.BarcodeFormat.QRCode,
            )
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise DomainError("invalid_qr_image", "無法讀取 QR 圖片", 422) from exc

    tokens = {result.text.strip() for result in results if result.text.strip()}
    if len(tokens) != 1:
        message = "圖片中找不到 QR Code" if not tokens else "請一次只拍一張 QR Code"
        raise DomainError("qr_not_found", message, 422)
    token = tokens.pop()
    if len(token) > _MAX_QR_TEXT_LENGTH:
        raise DomainError("invalid_qr_token", "QR Code 內容無效", 422)
    return token
