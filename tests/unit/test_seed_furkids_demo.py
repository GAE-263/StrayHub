import hashlib
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from scripts.seed_furkids_demo import (
    ANIMAL_SPECS,
    CARE_REPORT_COUNTS,
    ORGANIZATION_CODE,
    ORGANIZATION_NAME,
    ApprovedPhotoIngestor,
    DownloadedPhoto,
    PhotoIngestionResult,
    apply_primary_photo,
    build_seed_plan,
)
from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.infrastructure.storage.ports import ObjectScope


def test_furkids_seed_plan_has_fixed_organization_and_animals() -> None:
    plan = build_seed_plan()

    assert ORGANIZATION_CODE == "FURKIDS-ASIA"
    assert ORGANIZATION_NAME == "毛小孩幸福聯盟協會"
    assert [animal.name for animal in ANIMAL_SPECS] == [
        "獒黃妹",
        "獒一搓",
        "獒瓦蛤",
        "獒凱西",
        "柴福福",
    ]
    assert [animal.shelter_number for animal in ANIMAL_SPECS] == [
        "MTF-20140531-001",
        "MTF-20241213-001",
        "MTF-20240515-001",
        "MTF-20200605-001",
        "SBA-20170922-001",
    ]
    assert plan["organization"]["timezone"] == "Asia/Taipei"


def test_furkids_seed_plan_separates_source_facts_from_synthetic_data() -> None:
    plan = build_seed_plan()

    assert plan["source_derived"]["獒一搓"]["sex"] == "公犬"
    assert plan["source_derived"]["柴福福"]["intake_date"] == "2017-09-22"
    assert sum(CARE_REPORT_COUNTS.values()) == 20
    assert plan["synthetic_counts"] == {
        "medical_records": 8,
        "care_reminders": 3,
        "care_reports": 20,
    }
    assert "DailyReportableScope" not in plan["persistence_models"]


def test_furkids_seed_identifiers_are_unique_and_repeatable() -> None:
    first = build_seed_plan()
    second = build_seed_plan()

    assert first == second
    assert len({animal.id for animal in ANIMAL_SPECS}) == 5
    assert len({animal.shelter_number for animal in ANIMAL_SPECS}) == 5


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (12, 8), "orange").save(output, format="JPEG", exif=b"Exif\x00\x00")
    return output.getvalue()


@pytest.mark.asyncio
async def test_approved_photos_use_deterministic_keys_and_skip_second_download() -> None:
    source = _jpeg()
    spec = replace(ANIMAL_SPECS[0], source_sha256=hashlib.sha256(source).hexdigest())
    organization_id = uuid4()
    storage = InMemoryStorageFake()
    download_count = 0

    async def download(_url: str) -> DownloadedPhoto:
        nonlocal download_count
        download_count += 1
        return DownloadedPhoto(source, "image/jpeg")

    ingestor = ApprovedPhotoIngestor(storage, download=download)
    first = await ingestor.ensure(organization_id=organization_id, spec=spec)
    asset = SimpleNamespace(
        organization_id=organization_id,
        object_key=first.object_key,
        content_type=first.content_type,
        checksum=first.checksum,
        status="processed",
        purpose="animal_primary",
        exif_removed=True,
    )
    second = await ingestor.ensure(
        organization_id=organization_id,
        spec=spec,
        existing_asset=asset,
    )

    assert first.object_key == "furkids-demo/animals/MTF-20140531-001/primary.jpg"
    assert second.object_key == first.object_key
    assert first.downloaded is True
    assert second.downloaded is False
    assert download_count == 1
    assert b"Exif" not in await storage.get(
        scope=ObjectScope(organization_id), key=first.object_key
    )


@pytest.mark.asyncio
async def test_approved_photo_object_is_tenant_scoped() -> None:
    source = _jpeg()
    spec = replace(ANIMAL_SPECS[0], source_sha256=hashlib.sha256(source).hexdigest())
    organization_id = uuid4()
    other_organization_id = uuid4()
    storage = InMemoryStorageFake()

    async def download(_url: str) -> DownloadedPhoto:
        return DownloadedPhoto(source, "image/jpeg")

    result = await ApprovedPhotoIngestor(storage, download=download).ensure(
        organization_id=organization_id,
        spec=spec,
    )

    with pytest.raises(DomainError, match="不存在或無法存取"):
        await storage.get(
            scope=ObjectScope(other_organization_id),
            key=result.object_key,
        )


@pytest.mark.asyncio
async def test_approved_photo_download_failure_names_the_animal() -> None:
    async def fail(_url: str) -> DownloadedPhoto:
        raise OSError("network unavailable")

    with pytest.raises(RuntimeError, match="獒黃妹 核准原圖下載失敗"):
        await ApprovedPhotoIngestor(InMemoryStorageFake(), download=fail).ensure(
            organization_id=uuid4(),
            spec=ANIMAL_SPECS[0],
        )


def test_all_furkids_animals_have_approved_photo_metadata() -> None:
    assert all(spec.source_sha256 for spec in ANIMAL_SPECS)
    assert all(spec.photo_object_key.endswith("/primary.jpg") for spec in ANIMAL_SPECS)
    assert len({spec.photo_object_key for spec in ANIMAL_SPECS}) == 5


def test_current_photo_key_is_applied_only_to_its_intended_tenant_animal() -> None:
    organization_id = uuid4()
    for spec in ANIMAL_SPECS:
        animal = SimpleNamespace(
            organization_id=organization_id,
            shelter_number=spec.shelter_number,
            current_photo_key=None,
        )
        asset = SimpleNamespace(organization_id=organization_id)
        photo = PhotoIngestionResult(
            spec.photo_object_key,
            "image/jpeg",
            "a" * 64,
            True,
        )

        apply_primary_photo(
            organization_id=organization_id,
            spec=spec,
            animal=animal,
            asset=asset,
            photo=photo,
        )

        assert animal.current_photo_key == spec.photo_object_key
        assert asset.object_key == spec.photo_object_key
        assert asset.purpose == "animal_primary"
        assert asset.exif_removed is True

    wrong_tenant = SimpleNamespace(
        organization_id=uuid4(),
        shelter_number=ANIMAL_SPECS[0].shelter_number,
        current_photo_key=None,
    )
    with pytest.raises(RuntimeError, match="租戶不一致"):
        apply_primary_photo(
            organization_id=organization_id,
            spec=ANIMAL_SPECS[0],
            animal=wrong_tenant,
            asset=SimpleNamespace(organization_id=organization_id),
            photo=PhotoIngestionResult(
                ANIMAL_SPECS[0].photo_object_key,
                "image/jpeg",
                "b" * 64,
                True,
            ),
        )
