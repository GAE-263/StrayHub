from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.infrastructure.storage.ports import ObjectScope
from services.worker import worker
from services.worker.app.handlers.ai_job_runner import AIJobRunner
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter
from services.worker.app.persistence.session import create_worker_session_factory


def _database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


class _Fixture:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.user_id = uuid4()
        self.membership_id = uuid4()
        self.animal_id = uuid4()
        self.report_id = uuid4()
        self.job_id = uuid4()
        self.other_organization_id = uuid4()


async def _seed(fixture: _Fixture, *, subjects: tuple[str | None, ...]) -> InMemoryStorageFake:
    connection = await asyncpg.connect(_database_url())
    storage = InMemoryStorageFake()
    try:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO organizations (id, name, code, status, created_at, updated_at) "
                "VALUES ($1, 'AI Worker Shelter', $2, 'active', now(), now())",
                fixture.organization_id,
                f"AIW-{fixture.organization_id.hex[:10]}",
            )
            await connection.execute(
                "INSERT INTO users (id, username, display_name, status, created_at, updated_at) "
                "VALUES ($1, $2, 'AI Worker Volunteer', 'active', now(), now())",
                fixture.user_id,
                f"ai-worker-{fixture.user_id.hex[:10]}",
            )
            await connection.execute(
                "INSERT INTO organization_memberships "
                "(id, organization_id, user_id, role, status, valid_from, expires_at, "
                "created_at, updated_at) VALUES "
                "($1, $2, $3, 'VOLUNTEER', 'active', now() - interval '1 hour', "
                "now() + interval '7 days', now(), now())",
                fixture.membership_id,
                fixture.organization_id,
                fixture.user_id,
            )
            await connection.execute(
                "INSERT INTO animals "
                "(id, organization_id, name, shelter_number, status, created_at, updated_at) "
                "VALUES ($1, $2, '小灰', $3, 'active', now(), now())",
                fixture.animal_id,
                fixture.organization_id,
                f"AIW{fixture.animal_id.hex[:10]}",
            )
            await connection.execute(
                "INSERT INTO care_reports "
                "(id, organization_id, animal_id, volunteer_user_id, membership_id, answers, "
                "animal_name_snapshot, shelter_number_snapshot, note, status, ai_job_status, "
                "submitted_at, created_at, updated_at) VALUES "
                "($1, $2, $3, $4, $5, $6, '小灰', 'AIW-1', '原始內容', 'saved', "
                "'enqueued', now(), now(), now())",
                fixture.report_id,
                fixture.organization_id,
                fixture.animal_id,
                fixture.user_id,
                fixture.membership_id,
                json.dumps({"defecation": "defecation.normal"}),
            )
            await connection.execute(
                "INSERT INTO ai_processing_jobs "
                "(id, organization_id, job_type, target_type, target_id, status, provider, "
                "model_name, model_version, prompt_template_id, prompt_version, "
                "output_schema_version, execution_backend, retry_count, created_at, "
                "updated_at) VALUES "
                "($1, $2, 'care_observation', 'care_report', $3, 'pending_enqueue', 'mock', "
                "'model', 'v1', 'care-observation', 'v1', 'v1', 'celery', 0, now(), now())",
                fixture.job_id,
                fixture.organization_id,
                fixture.report_id,
            )
            for index, subject in enumerate(subjects):
                media_id = uuid4()
                key = f"reports/{fixture.report_id}/{index}.jpg"
                await connection.execute(
                    "INSERT INTO media_assets "
                    "(id, organization_id, object_key, content_type, checksum, status, purpose, "
                    "subject, exif_removed, created_at, updated_at) VALUES "
                    "($1, $2, $3, 'image/jpeg', $4, 'processed', 'care_report', $5, true, "
                    "now(), now())",
                    media_id,
                    fixture.organization_id,
                    key,
                    f"{index + 1:064x}",
                    subject,
                )
                await connection.execute(
                    "INSERT INTO care_report_media (id, report_id, media_asset_id) "
                    "VALUES ($1, $2, $3)",
                    uuid4(),
                    fixture.report_id,
                    media_id,
                )
                metadata = storage.metadata_for(
                    f"image-{index}".encode(),
                    content_type="image/jpeg",
                    checksum=f"{index + 1:064x}",
                )
                await storage.put(
                    scope=ObjectScope(fixture.organization_id),
                    key=key,
                    data=f"image-{index}".encode(),
                    metadata=metadata,
                )
    finally:
        await connection.close()
    return storage


async def _cleanup(fixture: _Fixture) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        async with connection.transaction():
            await connection.execute(
                "DELETE FROM ai_observations WHERE organization_id = $1", fixture.organization_id
            )
            await connection.execute(
                "DELETE FROM care_report_media WHERE report_id = $1", fixture.report_id
            )
            await connection.execute(
                "DELETE FROM media_assets WHERE organization_id = $1",
                fixture.other_organization_id,
            )
            for table in ("media_assets", "ai_processing_jobs", "care_reports", "animals"):
                await connection.execute(
                    f"DELETE FROM {table} WHERE organization_id = $1", fixture.organization_id
                )
            await connection.execute(
                "DELETE FROM organization_memberships WHERE organization_id = $1",
                fixture.organization_id,
            )
            await connection.execute("DELETE FROM users WHERE id = $1", fixture.user_id)
            await connection.execute(
                "DELETE FROM organizations WHERE id = $1", fixture.organization_id
            )
            await connection.execute(
                "DELETE FROM organizations WHERE id = $1", fixture.other_organization_id
            )
    finally:
        await connection.close()


async def _run(
    fixture: _Fixture, adapter: MockAIAdapter, storage, *, worker_id: str = "ai-test"
) -> int:
    factory = create_worker_session_factory()
    try:
        processed = await AIJobRunner(
            factory, worker_id=worker_id, client=adapter, storage=storage
        ).run_celery_job(fixture.organization_id, fixture.job_id, claim_token=worker_id)
        return int(processed)
    finally:
        await factory.kw["bind"].dispose()


async def _job(fixture: _Fixture) -> asyncpg.Record:
    connection = await asyncpg.connect(_database_url())
    try:
        return await connection.fetchrow(
            "SELECT status, retry_count, claim_token, raw_ai_output, available_at "
            "FROM ai_processing_jobs WHERE id = $1",
            fixture.job_id,
        )
    finally:
        await connection.close()


async def _report(fixture: _Fixture) -> asyncpg.Record:
    connection = await asyncpg.connect(_database_url())
    try:
        return await connection.fetchrow(
            "SELECT status, note, ai_job_status FROM care_reports WHERE id = $1",
            fixture.report_id,
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_runner_sends_only_stool_media_and_persists_observation() -> None:
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=("portrait", "stool", None))
    adapter = MockAIAdapter(result={"observations": []})
    try:
        assert await _run(fixture, adapter, storage) == 1
        assert len(adapter.requests) == 1
        row = await _job(fixture)
        assert row["status"] == "succeeded"
        assert row["claim_token"] is None
        assert json.loads(row["raw_ai_output"]) == {"observations": []}
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_legacy_polling_runner_ignores_celery_owned_care_job() -> None:
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=("stool",))
    adapter = MockAIAdapter(error=AssertionError("legacy runner must not invoke provider"))
    factory = create_worker_session_factory()
    try:
        processed = await AIJobRunner(
            factory,
            worker_id="legacy-worker",
            client=adapter,
            storage=storage,
        ).run_pending(fixture.organization_id)
        assert processed == 0
        assert adapter.requests == []
        row = await _job(fixture)
        assert row["status"] == "pending_enqueue"
        assert row["claim_token"] is None
    finally:
        await factory.kw["bind"].dispose()
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_competing_workers_claim_the_job_only_once() -> None:
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=("stool",))
    adapter = MockAIAdapter(result={"observations": []})
    try:
        processed = await asyncio.gather(
            _run(fixture, adapter, storage, worker_id="ai-a"),
            _run(fixture, adapter, storage, worker_id="ai-b"),
        )
        assert sum(processed) == 1
        assert len(adapter.requests) == 1
        assert (await _job(fixture))["status"] == "succeeded"
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_no_stool_media_skips_provider_and_records_safe_outcome() -> None:
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=("portrait", None))
    adapter = MockAIAdapter(error=AssertionError("provider must not be called"))
    try:
        await _run(fixture, adapter, storage)
        assert adapter.requests == []
        row = await _job(fixture)
        assert row["status"] == "succeeded"
        assert json.loads(row["raw_ai_output"]) == {"skipped": "no_stool_media"}
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_cross_organization_stool_media_is_filtered_before_download() -> None:
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=())
    connection = await asyncpg.connect(_database_url())
    try:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO organizations (id, name, code, status, created_at, updated_at) "
                "VALUES ($1, 'Other AI Shelter', $2, 'active', now(), now())",
                fixture.other_organization_id,
                f"AIO-{fixture.other_organization_id.hex[:10]}",
            )
            media_id = uuid4()
            await connection.execute(
                "INSERT INTO media_assets "
                "(id, organization_id, object_key, content_type, checksum, status, purpose, "
                "subject, exif_removed, created_at, updated_at) VALUES "
                "($1, $2, 'other/stool.jpg', 'image/jpeg', $3, 'processed', 'care_report', "
                "'stool', true, now(), now())",
                media_id,
                fixture.other_organization_id,
                "f" * 64,
            )
            await connection.execute(
                "INSERT INTO care_report_media (id, report_id, media_asset_id) VALUES ($1, $2, $3)",
                uuid4(),
                fixture.report_id,
                media_id,
            )
    finally:
        await connection.close()

    adapter = MockAIAdapter(error=AssertionError("cross-org provider call"))
    try:
        await _run(fixture, adapter, storage)
        assert adapter.requests == []
        assert json.loads((await _job(fixture))["raw_ai_output"]) == {"skipped": "no_stool_media"}
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_provider_failure_releases_claim_with_future_backoff() -> None:
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=("stool",))
    try:
        await _run(fixture, MockAIAdapter(error=TimeoutError()), storage)
        row = await _job(fixture)
        assert row["status"] == "retry_wait"
        assert row["retry_count"] == 1
        assert row["claim_token"] is None
        assert row["available_at"] > datetime.now(timezone.utc)
        report = await _report(fixture)
        assert report["status"] == "saved"
        assert report["note"] == "原始內容"
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_observation_persistence_failure_never_removes_report(monkeypatch) -> None:
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=("stool",))

    async def fail_observation(*_args, **_kwargs):
        raise RuntimeError("observation persistence unavailable")

    monkeypatch.setattr(AIJobRunner, "_observation_for", fail_observation)
    try:
        await _run(fixture, MockAIAdapter(), storage)
        assert (await _job(fixture))["status"] == "retry_wait"
        report = await _report(fixture)
        assert report["status"] == "saved"
        assert report["note"] == "原始內容"
        assert report["ai_job_status"] == "enqueued"
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_ai_iteration_continues_after_one_organization_failure(monkeypatch) -> None:
    organizations = [uuid4(), uuid4()]
    visited = []

    async def active(_factory):
        return organizations

    class Runner:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run_pending(self, organization_id):
            visited.append(organization_id)
            if organization_id == organizations[0]:
                raise RuntimeError("isolated")

    monkeypatch.setattr(worker, "active_organization_ids", active)
    monkeypatch.setattr(worker, "AIJobRunner", Runner)
    monkeypatch.setattr(
        worker,
        "get_worker_settings",
        lambda: SimpleNamespace(celery_ai_enabled=True),
    )

    await worker.run_ai_iteration(object(), worker_id="worker", client=object())

    assert visited == organizations


@pytest.mark.asyncio
async def test_worker_run_starts_ai_and_volunteer_loops(monkeypatch) -> None:
    ai_started = asyncio.Event()
    volunteer_started = asyncio.Event()

    async def ai(*_args, **_kwargs):
        ai_started.set()

    async def volunteer(*_args, **_kwargs):
        volunteer_started.set()

    monkeypatch.setattr(worker, "run_ai_iteration", ai)
    monkeypatch.setattr(worker, "run_volunteer_iteration", volunteer)
    task = asyncio.create_task(worker.run())
    try:
        await asyncio.wait_for(
            asyncio.gather(ai_started.wait(), volunteer_started.wait()), timeout=3
        )
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
