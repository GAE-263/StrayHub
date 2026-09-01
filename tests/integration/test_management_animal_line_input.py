from __future__ import annotations

import inspect
import os
from io import BytesIO
from uuid import uuid4

import asyncpg
import pytest
from PIL import Image
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.api.management_animals import (
    create_management_animal,
    create_management_animal_health_record,
)
from services.api.app.application.line_staff_animal_input_service import (
    LineStaffAnimalInputService,
    UploadedPhoto,
)
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.medical_care import MedicalRecord, MedicalRecordMedia
from sqlalchemy import select

DATABASE_URL = os.getenv(
    "STRAYHUB_TEST_DATABASE_URL",
    "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
)
pytestmark = pytest.mark.asyncio(loop_scope="session")


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), (120, 130, 140)).save(buffer, format="PNG")
    return buffer.getvalue()


def _photo() -> UploadedPhoto:
    return UploadedPhoto(data=_png_bytes(), content_type="image/png")


async def _seed() -> dict:
    await engine.dispose(close=False)
    ids = {name: uuid4() for name in ("org", "user", "membership", "animal")}
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        await connection.execute(
            """
            INSERT INTO organizations
                (id, name, code, status, timezone, timezone_version, created_at, updated_at)
            VALUES ($1, 'LINE Staff Input Test', $2, 'active', 'Asia/Taipei', 1, now(), now())
            """,
            ids["org"],
            f"LINEINPUT-{ids['org'].hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'LINE Staff', 'active', now(), now())
            """,
            ids["user"],
            f"lineinput-{ids['user'].hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, medical_care_access,
                 created_at, updated_at)
            VALUES ($1, $2, $3, 'STAFF', 'active', true, now(), now())
            """,
            ids["membership"],
            ids["org"],
            ids["user"],
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, created_at, updated_at)
            VALUES ($1, $2, '既有測試犬', $3, 'active', now(), now())
            """,
            ids["animal"],
            ids["org"],
            f"EXIST-{ids['animal'].hex[:6]}",
        )
    finally:
        await connection.close()
        await engine.dispose(close=False)
    return ids


async def _cleanup(ids: dict) -> None:
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        for table in (
            "medical_record_media",
            "medical_records",
            "media_assets",
            "audit_records",
            "animals",
        ):
            await connection.execute(f"DELETE FROM {table} WHERE organization_id = $1", ids["org"])
        await connection.execute(
            "DELETE FROM organization_memberships WHERE organization_id = $1", ids["org"]
        )
        await connection.execute("DELETE FROM users WHERE id = $1", ids["user"])
        await connection.execute("DELETE FROM organizations WHERE id = $1", ids["org"])
    finally:
        await connection.close()
        await engine.dispose(close=False)


async def test_create_animal_persists_record_and_photo() -> None:
    ids = await _seed()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            service = LineStaffAnimalInputService(session, ids["org"], InMemoryStorageFake())
            result = await service.create_animal(
                actor_user_id=ids["user"],
                animal_data={"tempAnimalId": "A20260827-1234", "name": "小黑"},
                photo=_photo(),
            )
            assert result["success"] is True

            animal = (
                await session.execute(
                    select(Animal).where(
                        Animal.organization_id == ids["org"],
                        Animal.name == "小黑",
                    )
                )
            ).scalar_one()
            assert animal.shelter_number == "A20260827-1234"
            assert animal.current_photo_key is not None
            assert str(animal.id) == result["animalId"]

            asset = (
                await session.execute(
                    select(MediaAsset).where(MediaAsset.object_key == animal.current_photo_key)
                )
            ).scalar_one()
            assert asset.purpose == "line_staff_animal"
            assert asset.exif_removed is True
    finally:
        await _cleanup(ids)


async def test_create_animal_rejects_blank_name() -> None:
    ids = await _seed()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            service = LineStaffAnimalInputService(session, ids["org"], InMemoryStorageFake())
            with pytest.raises(DomainError) as err:
                await service.create_animal(
                    actor_user_id=ids["user"],
                    animal_data={"name": "   "},
                    photo=_photo(),
                )
            assert err.value.status_code == 422
    finally:
        await _cleanup(ids)


async def test_create_animal_retry_with_same_shelter_number_fails_safely() -> None:
    ids = await _seed()
    shelter_number = f"RETRY-{ids['animal'].hex[:8]}"
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            service = LineStaffAnimalInputService(session, ids["org"], InMemoryStorageFake())
            await service.create_animal(
                actor_user_id=ids["user"],
                animal_data={"tempAnimalId": shelter_number, "name": "重試測試犬"},
                photo=_photo(),
            )
            await set_organization_scope(session, ids["org"])
            with pytest.raises(DomainError) as duplicate:
                await service.create_animal(
                    actor_user_id=ids["user"],
                    animal_data={"tempAnimalId": shelter_number, "name": "重試測試犬"},
                    photo=_photo(),
                )

            assert duplicate.value.code == "animal_already_exists"
            assert duplicate.value.status_code == 409
            count = len(
                (
                    await session.execute(
                        select(Animal).where(
                            Animal.organization_id == ids["org"],
                            Animal.shelter_number == shelter_number,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert count == 1
    finally:
        await _cleanup(ids)


async def test_health_record_lands_in_medical_records_with_status_label() -> None:
    ids = await _seed()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            service = LineStaffAnimalInputService(session, ids["org"], InMemoryStorageFake())
            result = await service.add_health_record(
                actor_user_id=ids["user"],
                animal_id=ids["animal"],
                health_record={"status": "needs_medical", "description": "右前腳輕微跛行"},
                submitted_at="2026-08-27T14:05:00+08:00",
                photo=_photo(),
            )
            assert result["success"] is True

            record = (
                await session.execute(
                    select(MedicalRecord).where(
                        MedicalRecord.organization_id == ids["org"],
                        MedicalRecord.animal_id == ids["animal"],
                    )
                )
            ).scalar_one()
            assert record.record_type == "other"
            assert record.title == "健康回報：需要就醫"
            assert record.content == "右前腳輕微跛行"
            assert str(record.id) == result["recordId"]

            media_count = len(
                (
                    await session.execute(
                        select(MedicalRecordMedia).where(
                            MedicalRecordMedia.medical_record_id == record.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert media_count == 1
    finally:
        await _cleanup(ids)


async def test_health_record_rejects_unknown_animal() -> None:
    ids = await _seed()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            service = LineStaffAnimalInputService(session, ids["org"], InMemoryStorageFake())
            with pytest.raises(DomainError) as err:
                await service.add_health_record(
                    actor_user_id=ids["user"],
                    animal_id=uuid4(),
                    health_record={"status": "healthy", "description": "狀況良好"},
                    submitted_at=None,
                    photo=None,
                )
            assert err.value.status_code == 404
    finally:
        await _cleanup(ids)


async def test_health_record_exact_retry_returns_original_record() -> None:
    ids = await _seed()
    payload = {"status": "healthy", "description": "網路重試只建立一次"}
    submitted_at = "2026-08-27T14:05:00+08:00"
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            service = LineStaffAnimalInputService(session, ids["org"], InMemoryStorageFake())
            first = await service.add_health_record(
                actor_user_id=ids["user"],
                animal_id=ids["animal"],
                health_record=payload,
                submitted_at=submitted_at,
                photo=None,
            )
            await set_organization_scope(session, ids["org"])
            replay = await service.add_health_record(
                actor_user_id=ids["user"],
                animal_id=ids["animal"],
                health_record=payload,
                submitted_at=submitted_at,
                photo=None,
            )

            assert replay == first
            count = len(
                (
                    await session.execute(
                        select(MedicalRecord).where(
                            MedicalRecord.organization_id == ids["org"],
                            MedicalRecord.animal_id == ids["animal"],
                            MedicalRecord.content == payload["description"],
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert count == 1
    finally:
        await _cleanup(ids)


async def test_line_input_requires_selected_shelter_and_staff_role() -> None:
    user_id = uuid4()
    with pytest.raises(DomainError) as missing:
        require_staff_or_admin(RequestContext(user_id, None, None, "STAFF"))
    assert missing.value.code == "shelter_context_required"

    with pytest.raises(DomainError) as volunteer:
        require_staff_or_admin(RequestContext(user_id, uuid4(), uuid4(), "VOLUNTEER"))
    assert volunteer.value.code == "management_access_denied"


async def test_line_input_contract_has_no_client_controlled_organization_field() -> None:
    for endpoint in (create_management_animal, create_management_animal_health_record):
        parameters = inspect.signature(endpoint).parameters
        assert "organization_id" not in parameters
        assert "organizationId" not in parameters
