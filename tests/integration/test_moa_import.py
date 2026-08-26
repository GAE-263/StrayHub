"""Real PostgreSQL, rolled back fixtures; never writes demo animals."""

import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from services.api.app.application.moa_import_service import MoaImportService, organization_identity
from services.api.app.domain.moa_import import select_records
from services.api.app.infrastructure.moa_open_data import decode_photo
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.animal_external_source import AnimalExternalSource
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.qr_code import AnimalQrCode
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def rows(shelter_id, ids=(1, 2), **changes):
    return [
        {
            "animal_id": i,
            "animal_shelter_pkid": shelter_id,
            "shelter_name": "測試收容所",
            "animal_kind": "狗",
            "animal_subid": f"TEST-{i}",
            "animal_Variety": " 米克斯 ",
            "animal_sex": "M",
            "animal_age": "ADULT",
            "animal_update": "2026/08/21",
            **changes,
        }
        for i in ids
    ]


def photo(color="orange"):
    stream = BytesIO()
    value = Image.new("RGB", (100, 100), color)
    value.paste("black", (10, 10, 30, 30))
    value.save(stream, "JPEG")
    return decode_photo(stream.getvalue(), declared_type="image/png")


@pytest.fixture
async def fixture():
    url = os.getenv(
        "STRAYHUB_TEST_DATABASE_URL", "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub"
    )
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1), pool_size=1, max_overflow=0
    )
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # SET LOCAL forces actual runtime RLS even when fixture connection is an admin.
        await connection.execute(text("SET LOCAL ROLE strayhub_runtime"))
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            async with session.begin():
                storage = InMemoryStorageFake()
                yield session, storage, str(uuid4().int)[:18]
        await transaction.rollback()
    # Reuse the exact same pool connection: transaction-local scope and role must be gone.
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                text("SELECT nullif(current_setting('app.current_org_id', true), '')")
            )
        ) is None
        assert (await connection.scalar(text("SELECT current_user"))) != "strayhub_runtime"
    await engine.dispose()


async def execute(fixture, records, *, limit=60, images=None, dry_run=False):
    session, storage, _ = fixture
    batch = select_records(records, shelter="測試收容所", kind="dog", limit=limit)
    return await MoaImportService(session, storage).run(
        batch=batch, shelter="測試收容所", limit=limit, photos=images, dry_run=dry_run
    )


async def test_idempotent_updates_images_qr_and_manual_fields(fixture):
    session, storage, shelter_id = fixture
    data = rows(shelter_id)
    images = {"1": photo(), "2": photo()}
    first = await execute(fixture, data, images=images)
    assert first["animals_created"] == first["qr_created"] == 2, first
    assert first["image_failures"] == 0, first
    ids = list((await session.scalars(select(Animal.id))).all())
    animal = await session.get(Animal, ids[0])
    animal.care_guidance = "人工照護提醒"
    second = await execute(fixture, data, images=images)
    assert second["animals_created"] == second["images_updated"] == second["qr_created"] == 0
    assert second["animals_unchanged"] == second["images_reused"] == second["qr_reused"] == 2
    assert set((await session.scalars(select(Animal.id))).all()) == set(ids)
    for model in (Animal, AnimalExternalSource, MediaAsset, AnimalQrCode):
        assert await session.scalar(select(func.count()).select_from(model)) == 2
    changed = await execute(
        fixture,
        rows(shelter_id, animal_Variety="貴賓犬", animal_sex="F", animal_update="2026/08/25"),
        images={"1": photo("blue"), "2": photo()},
    )
    assert changed["animals_updated"] == 2
    assert changed["images_updated"] == 1
    assert await session.scalar(select(func.count()).select_from(MediaAsset)) == 3
    assert animal.care_guidance == "人工照護提醒"
    assert animal.breed == "貴賓犬" and animal.sex == "female"
    assert animal.intake_date is None and animal.birth_date is None and animal.area_id is None
    mapping = await session.scalar(
        select(AnimalExternalSource).where(AnimalExternalSource.animal_id == animal.id)
    )
    assert mapping.source_updated_at.isoformat() == "2026-08-25"
    # Stored bytes are decoded JPEG, not the server's PNG declaration.
    for value, metadata in storage._objects.values():
        with Image.open(BytesIO(value)) as image:
            assert image.format == "JPEG" and not image.getexif()
        assert metadata.exif_removed and metadata.content_type == "image/jpeg"


async def test_presence_uses_full_set_not_selected_window(fixture):
    session, _, shelter_id = fixture
    await execute(fixture, rows(shelter_id))
    older = datetime.now(timezone.utc) - timedelta(days=1)
    mappings = list((await session.scalars(select(AnimalExternalSource))).all())
    for mapping in mappings:
        mapping.last_seen_at = older
    result = await execute(fixture, rows(shelter_id), limit=1)
    assert result["source_unavailable"] == 0
    assert all(m.last_seen_at > older for m in mappings)
    result = await execute(fixture, rows(shelter_id, ids=(2,)), limit=1)
    assert result["source_unavailable"] == 1
    assert {m.external_id: m.source_status for m in mappings} == {
        "1": "unavailable",
        "2": "present",
    }
    assert (
        await session.scalar(
            select(func.count()).select_from(Animal).where(Animal.status == "active")
        )
        == 2
    )


async def test_dry_run_has_no_writes_and_failures_retain_photo(fixture):
    session, storage, shelter_id = fixture
    summary = await execute(fixture, rows(shelter_id), dry_run=True)
    assert summary["animals_created"] == 2
    assert not storage._objects
    assert await session.scalar(select(func.count()).select_from(AnimalExternalSource)) == 0
    await execute(fixture, rows(shelter_id), images={"1": photo(), "2": "image_fetch_failed"})
    animal = await session.scalar(select(Animal).where(Animal.shelter_number == "TEST-1"))
    previous = animal.current_photo_key
    assert previous
    await execute(fixture, rows(shelter_id))
    assert animal.current_photo_key == previous
    animal.current_photo_key = "manually-managed/photo.jpg"
    result = await execute(fixture, rows(shelter_id), images={"1": photo("blue")})
    assert result["images_preserved_manual"] == 1
    assert animal.current_photo_key == "manually-managed/photo.jpg"


async def test_real_rls_hides_all_imported_resources_and_rejects_foreign_write(fixture):
    session, _, shelter_id = fixture
    result = await execute(fixture, rows(shelter_id), images={"1": photo(), "2": photo()})
    assert result["animals_created"] == 2, result
    org_id, _ = organization_identity(shelter_id)
    await set_organization_scope(session, uuid4())
    for model in (Animal, AnimalExternalSource, MediaAsset, AnimalQrCode):
        assert await session.scalar(select(func.count()).select_from(model)) == 0
    async with session.begin_nested() as savepoint:
        with pytest.raises(Exception, match="row-level security"):
            await session.execute(
                text("""INSERT INTO animals
                    (id, organization_id, name, status, created_at, updated_at,
                     birth_date_estimated)
                    VALUES (:id, :org, 'denied', 'active', now(), now(), false)"""),
                {"id": uuid4(), "org": org_id},
            )
        await savepoint.rollback()
    await set_organization_scope(session, org_id)
    assert await session.scalar(select(func.count()).select_from(AnimalExternalSource)) == 2


async def test_conflicting_external_identity_isolated_without_transferring_animal(fixture):
    session, _, shelter_id = fixture
    await execute(fixture, rows(shelter_id, ids=(1,)))
    foreign_shelter = str(int(shelter_id) + 1)
    result = await execute(fixture, rows(foreign_shelter, ids=(1, 3)))
    assert result["records_failed"] == 1
    assert result["animals_created"] == 1
    assert list((await session.scalars(select(Animal.shelter_number))).all()) == ["TEST-3"]
    await set_organization_scope(session, organization_identity(shelter_id)[0])
    assert list((await session.scalars(select(Animal.shelter_number))).all()) == ["TEST-1"]


async def test_corrupt_storage_never_sets_fake_photo_key(fixture):
    session, storage, shelter_id = fixture

    async def corrupted_get(**kwargs):
        return b"corrupt"

    storage.get = corrupted_get
    result = await execute(fixture, rows(shelter_id, ids=(1,)), images={"1": photo()})
    assert result["animals_created"] == 1
    assert result["image_failures"] == 1
    assert await session.scalar(select(Animal.current_photo_key)) is None
    assert await session.scalar(select(func.count()).select_from(MediaAsset)) == 0


async def test_same_name_breed_and_sex_in_two_shelters_do_not_collide(fixture):
    session, _, shelter_id = fixture
    await execute(fixture, rows(shelter_id, ids=(1,), animal_subid="SAME-NUMBER"))
    first = await session.scalar(select(Animal))
    original_mapping = await session.scalar(select(AnimalExternalSource))
    before = (original_mapping.source_status, original_mapping.last_seen_at)
    result = await execute(
        fixture, rows(str(int(shelter_id) + 1), ids=(2,), animal_subid="SAME-NUMBER")
    )
    second = await session.scalar(select(Animal))
    assert result["animals_created"] == 1
    assert first.name == second.name and first.breed == second.breed and first.sex == second.sex
    assert first.id != second.id and first.organization_id != second.organization_id
    assert (original_mapping.source_status, original_mapping.last_seen_at) == before


async def test_missing_names_keep_official_identity_across_shelters(fixture):
    session, _, shelter_id = fixture
    await execute(fixture, rows(shelter_id, ids=(1,), animal_subid=""))
    first = await session.scalar(select(Animal))
    await execute(fixture, rows(str(int(shelter_id) + 1), ids=(2,), animal_subid=""))
    second = await session.scalar(select(Animal))
    assert first.name == "MOA-1" and second.name == "MOA-2"
    assert first.id != second.id
