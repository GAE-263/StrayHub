from io import BytesIO

import pytest
from PIL import Image
from services.api.app.api.errors import DomainError
from services.api.app.application.media_sanitization import sanitize_image


def test_jpeg_is_reencoded_without_exif_and_checksum_is_returned() -> None:
    output = BytesIO()
    Image.new("RGB", (2, 2), "white").save(output, format="JPEG")

    cleaned, content_type, checksum = sanitize_image(
        output.getvalue(), declared_content_type="image/jpeg"
    )

    assert cleaned != b""
    assert content_type == "image/jpeg"
    assert len(checksum) == 64
    assert b"Exif" not in cleaned


def test_mismatched_or_unsupported_media_is_rejected() -> None:
    with pytest.raises(DomainError, match="不受支援"):
        sanitize_image(b"not an image", declared_content_type="application/octet-stream")
