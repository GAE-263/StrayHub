from io import BytesIO

import pytest
import zxingcpp
from PIL import Image
from services.api.app.api.errors import DomainError
from services.api.app.application.line_qr_image_decoder import decode_qr_image


def _qr_png(value: str) -> bytes:
    barcode = zxingcpp.create_barcode(value, zxingcpp.BarcodeFormat.QRCode)
    generated = zxingcpp.write_barcode_to_image(barcode, scale=10)
    image = Image.fromarray(generated)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_decodes_exact_qr_locator_text() -> None:
    assert decode_qr_image(_qr_png("opaque-animal-token")) == "opaque-animal-token"


@pytest.mark.parametrize("content", [b"", b"not an image"])
def test_rejects_empty_or_invalid_image(content: bytes) -> None:
    with pytest.raises(DomainError, match="QR"):
        decode_qr_image(content)


def test_rejects_image_without_qr() -> None:
    output = BytesIO()
    Image.new("RGB", (64, 64), "white").save(output, format="PNG")

    with pytest.raises(DomainError, match="找不到 QR"):
        decode_qr_image(output.getvalue())
