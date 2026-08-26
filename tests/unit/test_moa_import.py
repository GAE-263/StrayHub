from io import BytesIO

import httpx
import pytest
from PIL import Image
from services.api.app.domain.moa_import import normalize, select_records
from services.api.app.infrastructure.moa_open_data import (
    MoaOpenDataClient,
    decode_photo,
    validate_image_url,
)


def record(identifier=455402, **changes):
    return {
        "animal_id": identifier,
        "animal_subid": f"AAACG{identifier}",
        "animal_kind": "狗",
        "animal_shelter_pkid": 51,
        "shelter_name": "新北市新店區公立動物之家",
        "animal_Variety": "貴賓犬   ",
        "animal_sex": " M ",
        "animal_age": "ADULT",
        "animal_update": "2026/05/27",
        "animal_createtime": "2026/05/27",
        "album_file": "https://www.pet.gov.tw/upload/pic/1779857966208.png",
        "shelter_address": "新北市新店區安泰路235號",
        "shelter_tel": "02-22159462",
        **changes,
    }


def jpeg(color="orange"):
    stream = BytesIO()
    image = Image.new("RGB", (120, 100), color)
    image.paste("black", (10, 10, 30, 30))
    image.save(stream, "JPEG", exif=b"Exif\x00\x00")
    return stream.getvalue()


def test_normalization_never_invents_profile_or_cage():
    value = normalize(record())
    assert value.external_id == "455402"
    assert value.fields == {
        "name": "AAACG455402",
        "shelter_number": "AAACG455402",
        "breed": "貴賓犬",
        "sex": "male",
        "age_description": "成犬",
    }
    assert value.source_updated_at.isoformat() == "2026-05-27"
    assert "animal_createtime" in value.snapshot
    assert "intake_date" not in value.fields


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("M", "male"),
        ("公", "male"),
        ("F", "female"),
        ("母", "female"),
        ("N", "unknown"),
        ("", "unknown"),
        ("unknown", "unknown"),
    ],
)
def test_official_sex_only(raw, expected):
    assert normalize(record(animal_sex=raw)).fields["sex"] == expected


def test_missing_age_breed_image_name_fallback():
    value = normalize(record(animal_age="", animal_Variety=" ", album_file="", animal_subid=""))
    assert value.fields["age_description"] is None
    assert value.fields["breed"] is None
    assert value.image_url is None
    assert value.fields["name"] == "MOA-455402"


def test_filter_exact_shelter_dogs_and_order_before_limit():
    rows = [
        record(1),
        record(2, animal_update="2026/08/21"),
        record(3, animal_kind="貓"),
        record(4, shelter_name="新北市五股區公立動物之家"),
        record(5, shelter_name=" 新北市新店區公立動物之家  "),
    ]
    batch = select_records(rows, shelter="新北市新店區公立動物之家", kind="dog", limit=1)
    assert batch.eligible_count == 3
    assert batch.present_ids == {"1", "2", "5"}
    assert [r.external_id for r in batch.selected] == ["2"]


def test_duplicate_identity_or_invalid_id_fails_before_presence_sync():
    with pytest.raises(ValueError):
        select_records([record(), record()], shelter=record()["shelter_name"], kind="dog", limit=60)
    with pytest.raises(ValueError):
        normalize(record(animal_id="bad"))


@pytest.mark.parametrize("limit", [0, 61, -1])
def test_limit_is_bounded(limit):
    with pytest.raises(ValueError):
        select_records([record()], shelter=record()["shelter_name"], kind="dog", limit=limit)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a.jpg",
        "https://evil.example/a.png",
        "https://www.pet.gov.tw/images/default.png",
        "https://user:secret@www.pet.gov.tw/upload/pic/a.png",
    ],
)
def test_untrusted_or_placeholder_url_rejected(url):
    with pytest.raises(ValueError):
        validate_image_url(url)


def test_verified_png_url_and_http_mime_with_jpeg_bytes():
    # Reproduces all three verified MOA examples without committing source photos.
    photo = decode_photo(jpeg(), declared_type="image/png")
    assert photo.content_type == "image/jpeg"
    assert photo.extension == "jpg"
    assert photo.width == 120 and photo.height == 100
    assert photo.source_checksum


def test_invalid_image_and_tiny_placeholder_rejected():
    with pytest.raises(ValueError):
        decode_photo(b"not an image", declared_type="image/png")
    output = BytesIO()
    Image.new("RGB", (1, 1)).save(output, "PNG")
    with pytest.raises(ValueError):
        decode_photo(output.getvalue(), declared_type="image/png")


async def test_http_png_declaration_with_actual_jpeg_and_bounded_retry():
    calls = []

    def respond(request):
        calls.append(request.url)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, headers={"content-type": "image/png"}, content=jpeg())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        result = await MoaOpenDataClient(http).fetch_photo(record()["album_file"])
    assert len(calls) == 3 and result.content_type == "image/jpeg"


async def test_network_failure_retries_only_three_times():
    calls = []

    def respond(request):
        calls.append(request.url)
        raise httpx.ReadTimeout("test timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ValueError, match="dataset_fetch_failed"):
            await MoaOpenDataClient(http).fetch_records()
    assert len(calls) == 3


async def test_redirect_cannot_escape_official_image_host():
    calls = []

    def respond(request):
        calls.append(request.url)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ValueError, match="untrusted"):
            await MoaOpenDataClient(http).fetch_photo(record()["album_file"])
    assert len(calls) == 1


async def test_oversized_response_is_bounded():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"12345"))
    ) as http:
        with pytest.raises(ValueError, match="source_response_too_large"):
            await MoaOpenDataClient(http)._get(record()["album_file"], image=True, max_bytes=4)
