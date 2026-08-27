"""Name ownership and provenance on real PostgreSQL runtime-role/RLS, rolled back."""

import json

import pytest
from services.api.app.application.audit_service import AuditService
from services.api.app.application.moa_import_service import MoaImportService
from services.api.app.domain.moa_import import MoaNameObservation, select_records
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.animal_external_source import AnimalExternalSource
from sqlalchemy import select, text

from tests.integration.test_moa_import import fixture as fixture
from tests.integration.test_moa_import import photo, rows


async def sync(fixture, observations, *, dry_run=False, data=None):
    session, storage, shelter = fixture
    batch = select_records(data or rows(shelter), shelter="測試收容所", kind="dog", limit=60)
    return await MoaImportService(session, storage).run(
        batch=batch,
        shelter="測試收容所",
        limit=60,
        photos={"1": photo(), "2": photo()},
        names=observations,
        dry_run=dry_run,
    )


async def pair(session):
    animal = await session.scalar(select(Animal).where(Animal.shelter_number == "TEST-1"))
    mapping = await session.scalar(
        select(AnimalExternalSource).where(AnimalExternalSource.animal_id == animal.id)
    )
    return animal, mapping


async def test_owned_update_manual_conflict_and_idempotency(fixture):
    session, _, _ = fixture
    empty = MoaNameObservation("", None)
    await sync(fixture, {"1": empty, "2": empty})
    animal, mapping = await pair(session)
    assert animal.name == "TEST-1"
    assert mapping.source_snapshot["name_enrichment"]["status"] == "official_empty"
    official = MoaNameObservation("歪歪 15M029", "歪歪 15M029")
    first = await sync(fixture, {"1": official, "2": empty})
    assert first["names_official_applied"] == 1 and animal.name == "歪歪 15M029"
    second = await sync(fixture, {"1": official, "2": empty})
    assert second["names_official_unchanged"] == 1
    assert second["animals_unchanged"] == 2 and second["name_conflicts_preserved"] == 0
    animal.name = "小黑"
    await session.flush()
    conflict = await sync(fixture, {"1": official, "2": empty})
    assert conflict["name_conflicts_preserved"] == 1 and animal.name == "小黑"
    meta = mapping.source_snapshot["name_enrichment"]
    assert meta["normalized_name"] == "歪歪 15M029" and meta["last_applied_name"] == "歪歪 15M029"
    assert meta["status"] == "conflict"
    assert (await sync(fixture, {"1": official, "2": empty}))["name_conflicts_preserved"] == 1


async def test_manual_edit_before_first_official_name_is_preserved_in_plan_and_sync(fixture):
    session, _, _ = fixture
    empty = MoaNameObservation("", None)
    await sync(fixture, {"1": empty, "2": empty})
    animal, mapping = await pair(session)
    animal.name = "小黑"
    await session.flush()
    observations = {"1": MoaNameObservation("歪歪 15M029", "歪歪 15M029"), "2": empty}
    plan = await sync(fixture, observations, dry_run=True)
    assert plan["name_conflicts_preserved"] == 1 and animal.name == "小黑"
    assert mapping.source_snapshot["name_enrichment"]["status"] == "official_empty"
    result = await sync(fixture, observations)
    assert result["name_conflicts_preserved"] == 1 and animal.name == "小黑"
    meta = mapping.source_snapshot["name_enrichment"]
    assert meta["last_applied_name"] == "TEST-1"
    assert meta["normalized_name"] == "歪歪 15M029" and meta["status"] == "conflict"


async def test_authoritative_empty_does_not_downgrade_previous_official_name(fixture):
    session, _, _ = fixture
    empty = MoaNameObservation("", None)
    await sync(fixture, {"1": MoaNameObservation("來福", "來福"), "2": empty})
    animal, mapping = await pair(session)
    result = await sync(fixture, {"1": empty, "2": empty})
    assert animal.name == "來福" and result["name_enrichment_failures"] == 0
    meta = mapping.source_snapshot["name_enrichment"]
    assert meta["status"] == "official_empty" and meta["normalized_name"] is None
    assert meta["last_applied_name"] == meta["last_successful_name"] == "來福"


@pytest.mark.parametrize(
    "error", ["name_request_failed", "name_invalid_response", "name_identity_mismatch"]
)
async def test_failed_enrichment_never_downgrades_and_batch_continues(fixture, error):
    session, _, _ = fixture
    official = MoaNameObservation("歪歪 15M029", "歪歪 15M029")
    await sync(fixture, {"1": official, "2": MoaNameObservation("", None)})
    animal, mapping = await pair(session)
    result = await sync(
        fixture,
        {"1": MoaNameObservation(error_code=error), "2": MoaNameObservation("來福", "來福")},
    )
    assert result["name_enrichment_failures"] == 1 and result["names_official_applied"] == 1
    assert animal.name == "歪歪 15M029"
    meta = mapping.source_snapshot["name_enrichment"]
    assert meta["status"] == "failed" and meta["last_applied_name"] == "歪歪 15M029"
    assert meta["last_successful_name"] == "歪歪 15M029"


@pytest.mark.parametrize("evidence", ["importer", "missing", "manual", "manual_same_fallback"])
async def test_legacy_bootstrap_requires_import_audit_and_no_manual_name_evidence(
    fixture, evidence
):
    session, _, _ = fixture
    await sync(fixture, {"1": MoaNameObservation("", None), "2": MoaNameObservation("", None)})
    animal, mapping = await pair(session)
    mapping.source_snapshot = {
        k: v for k, v in mapping.source_snapshot.items() if k != "name_enrichment"
    }
    if evidence == "missing":
        # No DELETE privilege expansion: hide the import evidence through its resource ID.
        await session.execute(
            text("UPDATE audit_records SET resource_id=NULL WHERE resource_id=:id"),
            {"id": animal.id},
        )
    elif evidence.startswith("manual"):
        await AuditService(session).record(
            organization_id=animal.organization_id,
            actor_user_id=None,
            actor_reference="fixture_editor",
            action="animal.profile_updated",
            resource_type="Animal",
            resource_id=animal.id,
            source_channel="management",
            before={"name": "小黑"},
            after={"name": "TEST-1"},
        )
        if evidence == "manual":
            animal.name = "小黑"
    await session.flush()
    result = await sync(
        fixture,
        {"1": MoaNameObservation("歪歪 15M029", "歪歪 15M029"), "2": MoaNameObservation("", None)},
    )
    assert result["names_official_applied"] == (1 if evidence == "importer" else 0)
    assert result["name_conflicts_preserved"] == (0 if evidence == "importer" else 1)
    if evidence != "importer":
        assert mapping.source_snapshot["name_enrichment"]["last_applied_name"] is None
        assert (
            await sync(
                fixture,
                {
                    "1": MoaNameObservation("歪歪 15M029", "歪歪 15M029"),
                    "2": MoaNameObservation("", None),
                },
            )
        )["name_conflicts_preserved"] == 1


async def test_dry_run_and_snapshot_bound(fixture):
    session, storage, shelter = fixture
    empty = {"1": MoaNameObservation("", None), "2": MoaNameObservation("", None)}
    await sync(fixture, empty)
    animal, mapping = await pair(session)
    before = json.dumps(mapping.source_snapshot, sort_keys=True)
    result = await sync(
        fixture,
        {"1": MoaNameObservation("歪歪 15M029", "歪歪 15M029"), "2": empty["2"]},
        dry_run=True,
    )
    assert result["names_official_applied"] == 1
    assert animal.name == "TEST-1" and json.dumps(mapping.source_snapshot, sort_keys=True) == before
    assert result["animals_updated"] == 1
    long_data = rows(shelter, animal_remark="中" * 1000, animal_caption="文" * 1000)
    await sync(
        fixture, {"1": MoaNameObservation(" 名字\u00a0 ", "名字"), "2": empty["2"]}, data=long_data
    )
    assert len(json.dumps(mapping.source_snapshot, ensure_ascii=False).encode()) <= 32768
    assert (
        await session.scalar(
            text("SELECT max(octet_length(source_snapshot::text)) FROM animal_external_sources")
        )
        <= 32768
    )


async def test_oversized_metadata_rolls_back_only_that_record(fixture):
    session, _, _ = fixture
    await sync(fixture, {"1": MoaNameObservation("", None), "2": MoaNameObservation("", None)})
    animal, mapping = await pair(session)
    original = json.dumps(mapping.source_snapshot, sort_keys=True)
    result = await sync(
        fixture,
        {
            "1": MoaNameObservation("x" * 40000, "bad"),
            "2": MoaNameObservation("來福", "來福"),
        },
    )
    assert result["records_failed"] == 1 and result["names_official_applied"] == 1
    await session.refresh(animal)
    await session.refresh(mapping)
    assert animal.name == "TEST-1"
    assert json.dumps(mapping.source_snapshot, sort_keys=True) == original
