from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.api import management_animals
from services.api.app.api.errors import DomainError
from services.api.app.application.line_staff_animal_input_service import (
    ALLOWED_PHOTO_TYPES,
    HEALTH_STATUS_LABELS,
    LineStaffAnimalInputService,
    UploadedPhoto,
)


def test_health_status_labels_cover_frontend_config_values() -> None:
    # 對映前端 config 定義的五種健康狀態；缺一都可能讓標題失真。
    assert HEALTH_STATUS_LABELS == {
        "healthy": "健康",
        "needs_medical": "需要就醫",
        "in_treatment": "治療中",
        "neutered": "已絕育",
        "under_observation": "觀察中",
    }


def test_resolve_occurred_at_preserves_explicit_offset() -> None:
    result = LineStaffAnimalInputService._resolve_occurred_at(
        "2026-08-27T14:05:00+08:00", "Asia/Taipei"
    )
    assert result.tzinfo == timezone.utc
    # 14:05 台北 (+08:00) == 06:05 UTC
    assert result == datetime(2026, 8, 27, 6, 5, tzinfo=timezone.utc)


def test_resolve_occurred_at_assumes_org_timezone_when_naive() -> None:
    result = LineStaffAnimalInputService._resolve_occurred_at("2026-08-27T14:05:00", "Asia/Taipei")
    assert result == datetime(2026, 8, 27, 6, 5, tzinfo=timezone.utc)


def test_resolve_occurred_at_falls_back_to_now_on_missing_or_bad_input() -> None:
    before = datetime.now(timezone.utc)
    for value in (None, "", "not-a-timestamp"):
        result = LineStaffAnimalInputService._resolve_occurred_at(value, "Asia/Taipei")
        assert result.tzinfo == timezone.utc
        assert result >= before


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["text/html", "image/svg+xml", "application/pdf"])
async def test_create_rejects_non_raster_photo_types(content_type: str) -> None:
    service = LineStaffAnimalInputService(object(), uuid4(), object())

    with pytest.raises(DomainError, match="照片格式不支援"):
        await service.create_animal(
            actor_user_id=uuid4(),
            animal_data={"name": "小白"},
            photo=UploadedPhoto(data=b"not-an-image", content_type=content_type),
        )


@pytest.mark.asyncio
async def test_create_rejects_overlong_required_fields_before_storage() -> None:
    service = LineStaffAnimalInputService(object(), uuid4(), object())

    with pytest.raises(DomainError, match="動物名稱過長"):
        await service.create_animal(
            actor_user_id=uuid4(),
            animal_data={"name": "犬" * 201},
            photo=UploadedPhoto(data=b"x", content_type=next(iter(ALLOWED_PHOTO_TYPES))),
        )


@pytest.mark.asyncio
async def test_health_update_rejects_status_outside_allowlist() -> None:
    service = LineStaffAnimalInputService(object(), uuid4(), object())

    with pytest.raises(DomainError, match="允許清單"):
        await service.add_health_record(
            actor_user_id=uuid4(),
            animal_id=uuid4(),
            health_record={"status": "javascript:alert(1)", "description": "惡意狀態"},
            submitted_at=None,
            photo=None,
        )


@pytest.mark.asyncio
async def test_upload_size_limit_is_enforced_before_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Upload:
        content_type = "image/png"

        async def read(self) -> bytes:
            return b"1234"

    monkeypatch.setattr(management_animals, "MAX_PHOTO_BYTES", 3)

    with pytest.raises(DomainError, match="超過允許大小"):
        await management_animals._read_photo(Upload())
