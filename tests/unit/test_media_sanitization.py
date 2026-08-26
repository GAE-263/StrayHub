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


@pytest.mark.parametrize(
    "fmt,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")]
)
def test_all_supported_formats_remove_source_exif(fmt, mime):
    output = BytesIO()
    exif = Image.Exif()
    exif[315] = "source-author-metadata"
    Image.new("RGB", (40, 40), "orange").save(output, format=fmt, exif=exif)
    with Image.open(BytesIO(output.getvalue())) as original:
        assert original.getexif()[315] == "source-author-metadata"
    cleaned, _, _ = sanitize_image(output.getvalue(), declared_content_type=mime)
    with Image.open(BytesIO(cleaned)) as image:
        assert not image.getexif()
