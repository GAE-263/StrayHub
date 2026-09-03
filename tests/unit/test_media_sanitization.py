import hashlib
import warnings
from io import BytesIO

import pytest
from PIL import Image
from services.api.app.api.errors import DomainError
from services.api.app.application import media_sanitization
from services.api.app.application.media_sanitization import (
    MAX_FINAL_IMAGE_BYTES,
    MAX_IMAGE_BYTES,
    sanitize_image,
)


class _HeaderOnlyImage:
    def __init__(self, *, image_format: str, size: tuple[int, int]) -> None:
        self.format = image_format
        self.size = size
        self.load_called = False

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def load(self) -> None:
        self.load_called = True

    def copy(self):
        return Image.new("RGB", (1, 1), "white")


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


def test_input_byte_limit_is_checked_before_image_open(monkeypatch) -> None:
    opened = False

    def fail_if_opened(_stream):
        nonlocal opened
        opened = True
        raise AssertionError("Image.open must not run for oversized input")

    monkeypatch.setattr(media_sanitization.Image, "open", fail_if_opened)

    with pytest.raises(DomainError, match="超過允許大小"):
        sanitize_image(b"x" * (MAX_IMAGE_BYTES + 1), declared_content_type="image/jpeg")

    assert opened is False


def test_pixel_gate_rejects_before_full_decode(monkeypatch) -> None:
    source = _HeaderOnlyImage(image_format="JPEG", size=(5_001, 5_000))
    monkeypatch.setattr(media_sanitization.Image, "open", lambda _stream: source)

    with pytest.raises(DomainError, match="解析度"):
        sanitize_image(
            b"header",
            declared_content_type="image/jpeg",
            output_policy="growth_diary_webp",
        )

    assert source.load_called is False


def test_actual_format_is_validated_before_full_decode(monkeypatch) -> None:
    source = _HeaderOnlyImage(image_format="PNG", size=(2, 2))
    monkeypatch.setattr(media_sanitization.Image, "open", lambda _stream: source)

    with pytest.raises(DomainError, match="實際格式與宣告不一致"):
        sanitize_image(b"header", declared_content_type="image/jpeg")

    assert source.load_called is False


@pytest.mark.parametrize("signal", ["warning", "error"])
def test_pillow_decompression_bomb_signals_fail_closed(monkeypatch, signal) -> None:
    def bomb(_stream):
        if signal == "warning":
            warnings.warn("decompression bomb", Image.DecompressionBombWarning, stacklevel=2)
        raise Image.DecompressionBombError("decompression bomb")

    monkeypatch.setattr(media_sanitization.Image, "open", bomb)

    with pytest.raises(DomainError, match="解析度"):
        sanitize_image(
            b"header",
            declared_content_type="image/jpeg",
            output_policy="growth_diary_webp",
        )


def _image_bytes(
    *,
    fmt: str,
    size: tuple[int, int] = (40, 20),
    mode: str = "RGB",
    color="orange",
    **save_options,
) -> bytes:
    output = BytesIO()
    Image.new(mode, size, color).save(output, format=fmt, **save_options)
    return output.getvalue()


@pytest.mark.parametrize(
    ("fmt", "mime"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_growth_diary_normalizes_supported_inputs_to_webp(fmt, mime) -> None:
    cleaned, content_type, checksum = sanitize_image(
        _image_bytes(fmt=fmt),
        declared_content_type=mime,
        output_policy="growth_diary_webp",
    )

    with Image.open(BytesIO(cleaned)) as image:
        assert image.format == "WEBP"
        assert image.size == (40, 20), "small images must not be upscaled"
        assert image.n_frames == 1
    assert content_type == "image/webp"
    assert len(cleaned) <= MAX_FINAL_IMAGE_BYTES
    assert checksum == hashlib.sha256(cleaned).hexdigest()


def test_growth_diary_webp_uses_deterministic_three_step_fallback(monkeypatch) -> None:
    attempts: list[tuple[tuple[int, int], int]] = []

    def controlled_encoder(image, *, quality):
        attempts.append((image.size, quality))
        return b"x" * (MAX_FINAL_IMAGE_BYTES + 1) if quality != 68 else b"final"

    monkeypatch.setattr(media_sanitization, "_encode_webp", controlled_encoder)

    cleaned, content_type, checksum = sanitize_image(
        _image_bytes(fmt="JPEG", size=(2_000, 1_000)),
        declared_content_type="image/jpeg",
        output_policy="growth_diary_webp",
    )

    assert attempts == [((1_600, 800), 82), ((1_600, 800), 72), ((1_280, 640), 68)]
    assert cleaned == b"final"
    assert content_type == "image/webp"
    assert checksum == hashlib.sha256(b"final").hexdigest()


def test_growth_diary_webp_rejects_when_all_fallbacks_exceed_limit(monkeypatch) -> None:
    attempts: list[tuple[tuple[int, int], int]] = []

    def oversized_encoder(image, *, quality):
        attempts.append((image.size, quality))
        return b"x" * (MAX_FINAL_IMAGE_BYTES + 1)

    monkeypatch.setattr(media_sanitization, "_encode_webp", oversized_encoder)

    with pytest.raises(DomainError, match="壓縮後仍超過允許大小"):
        sanitize_image(
            _image_bytes(fmt="PNG", size=(2_000, 1_000)),
            declared_content_type="image/png",
            output_policy="growth_diary_webp",
        )

    assert attempts == [((1_600, 800), 82), ((1_600, 800), 72), ((1_280, 640), 68)]


def test_growth_diary_webp_applies_exif_orientation_and_removes_metadata() -> None:
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "source-author-metadata"

    cleaned, _, _ = sanitize_image(
        _image_bytes(fmt="JPEG", size=(40, 20), exif=exif),
        declared_content_type="image/jpeg",
        output_policy="growth_diary_webp",
    )

    with Image.open(BytesIO(cleaned)) as image:
        assert image.size == (20, 40)
        assert not image.getexif()


def test_growth_diary_webp_preserves_alpha() -> None:
    cleaned, _, _ = sanitize_image(
        _image_bytes(fmt="PNG", mode="RGBA", color=(20, 40, 60, 0)),
        declared_content_type="image/png",
        output_policy="growth_diary_webp",
    )

    with Image.open(BytesIO(cleaned)) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0


def test_growth_diary_webp_keeps_only_first_animation_frame() -> None:
    output = BytesIO()
    first = Image.new("RGB", (20, 20), "red")
    second = Image.new("RGB", (20, 20), "blue")
    first.save(
        output,
        format="WEBP",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )

    cleaned, _, _ = sanitize_image(
        output.getvalue(),
        declared_content_type="image/webp",
        output_policy="growth_diary_webp",
    )

    with Image.open(BytesIO(cleaned)) as image:
        red, _green, blue = image.convert("RGB").getpixel((10, 10))
        assert image.n_frames == 1
        assert red > blue
