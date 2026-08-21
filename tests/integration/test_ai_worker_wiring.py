"""AIJobHandler 曾經完整實作卻從未被 Worker 呼叫，Job 永遠停在 pending_enqueue。

這些測試守住接線本身：run() 必須啟動 AI 迴圈，而 AIJobRunner 必須真的把
資料庫裡的 Job 帶到 Handler 再把結果寫回去。只測 Handler 是抓不到這個缺陷的。
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.worker import worker
from services.worker.app.handlers.ai_job_runner import AI_MAX_RETRY, AIJobRunner
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter
from services.worker.app.persistence.session import create_worker_session_factory

TEST_OPTION_CODE = "feeding.worker_wiring_probe"


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


class _Fixture:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.user_id = uuid4()
        self.membership_id = uuid4()
        self.area_id = uuid4()
        self.animal_id = uuid4()
        self.report_id = uuid4()
        self.job_id = uuid4()


async def _seed(connection: asyncpg.Connection, fixture: _Fixture) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await connection.execute("BEGIN")
    await connection.execute(
        """
        INSERT INTO organizations (id, name, code, status, created_at, updated_at)
        VALUES ($1, 'AI Wiring Shelter', $2, 'active', now(), now())
        """,
        fixture.organization_id,
        f"AIW-{fixture.organization_id.hex[:10]}",
    )
    await connection.execute(
        """
        INSERT INTO users (id, username, display_name, status, created_at, updated_at)
        VALUES ($1, $2, 'AI Wiring Volunteer', 'active', now(), now())
        """,
        fixture.user_id,
        f"ai-wiring-{fixture.user_id.hex[:10]}",
    )
    await connection.execute(
        """
        INSERT INTO organization_memberships
            (id, organization_id, user_id, role, status, created_at, updated_at,
             valid_from, expires_at)
        VALUES ($1, $2, $3, 'VOLUNTEER', 'active', now(), now(),
                now() - interval '1 hour', now() + interval '7 days')
        """,
        fixture.membership_id,
        fixture.organization_id,
        fixture.user_id,
    )
    await connection.execute(
        """
        INSERT INTO shelter_areas
            (id, organization_id, name, area_type, status, created_at, updated_at)
        VALUES ($1, $2, 'AI Wiring Cage', 'cage', 'active', now(), now())
        """,
        fixture.area_id,
        fixture.organization_id,
    )
    await connection.execute(
        """
        INSERT INTO animals
            (id, organization_id, name, shelter_number, area_id, status, created_at, updated_at)
        VALUES ($1, $2, '小灰', $3, $4, 'active', now(), now())
        """,
        fixture.animal_id,
        fixture.organization_id,
        f"AIW{fixture.animal_id.hex[:11]}",
        fixture.area_id,
    )
    category_id = uuid4()
    await connection.execute(
        """
        INSERT INTO observation_categories
            (id, organization_id, code, display_name, description, status, display_order,
             created_at, updated_at)
        VALUES ($1, $2, $3, '餵食', '', 'active', 0, now(), now())
        """,
        category_id,
        fixture.organization_id,
        f"feeding_probe_{category_id.hex[:8]}",
    )
    await connection.execute(
        """
        INSERT INTO observation_options
            (id, category_id, organization_id, code, display_name, description, status,
             display_order, requires_note, created_at, updated_at)
        VALUES ($1, $2, $3, $4, '正常進食', '', 'active', 0, false, now(), now())
        """,
        uuid4(),
        category_id,
        fixture.organization_id,
        TEST_OPTION_CODE,
    )
    await connection.execute(
        """
        INSERT INTO care_reports
            (id, organization_id, animal_id, volunteer_user_id, membership_id, answers,
             animal_name_snapshot, shelter_number_snapshot, note, status, ai_job_status,
             submitted_at, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, '小灰', 'AIW-0001', $7, 'saved', 'enqueued',
                now(), now(), now())
        """,
        fixture.report_id,
        fixture.organization_id,
        fixture.animal_id,
        fixture.user_id,
        fixture.membership_id,
        json.dumps({"feeding": TEST_OPTION_CODE}),
        "志工原始心得",
    )
    await connection.execute(
        """
        INSERT INTO ai_processing_jobs
            (id, organization_id, job_type, target_type, target_id, status, provider,
             model_name, model_version, prompt_template_id, prompt_version,
             output_schema_version, retry_count, created_at, updated_at)
        VALUES ($1, $2, 'care_observation', 'care_report', $3, 'pending_enqueue', 'mock',
                'mock-observation-model', 'local-v1', 'care-observation', 'local-v1',
                'v1', 0, now(), now())
        """,
        fixture.job_id,
        fixture.organization_id,
        fixture.report_id,
    )
    await connection.execute("COMMIT")
    assert now is not None


async def _cleanup(fixture: _Fixture) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        for table in (
            "ai_observations",
            "ai_call_logs",
            "ai_processing_jobs",
            "care_reports",
            "observation_options",
            "observation_categories",
            "animals",
            "shelter_areas",
            "organization_memberships",
        ):
            await connection.execute(
                f"DELETE FROM {table} WHERE organization_id = $1", fixture.organization_id
            )
        await connection.execute("DELETE FROM users WHERE id = $1", fixture.user_id)
        await connection.execute("DELETE FROM organizations WHERE id = $1", fixture.organization_id)
        await connection.execute("COMMIT")
    finally:
        await connection.close()


async def _job_row(fixture: _Fixture) -> asyncpg.Record:
    connection = await asyncpg.connect(_database_url())
    try:
        return await connection.fetchrow(
            "SELECT status, claim_token, claimed_by, retry_count, failure_reason,"
            " raw_ai_output, validation_result, available_at"
            " FROM ai_processing_jobs WHERE id = $1",
            fixture.job_id,
        )
    finally:
        await connection.close()


async def _report_status(fixture: _Fixture) -> str:
    connection = await asyncpg.connect(_database_url())
    try:
        return await connection.fetchval(
            "SELECT ai_job_status FROM care_reports WHERE id = $1", fixture.report_id
        )
    finally:
        await connection.close()


async def _observations(fixture: _Fixture) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(_database_url())
    try:
        return list(
            await connection.fetch(
                "SELECT status, source_type, source_id, raw_ai_output,"
                " validated_ai_observation"
                " FROM ai_observations WHERE job_id = $1",
                fixture.job_id,
            )
        )
    finally:
        await connection.close()


async def _run_runner(fixture: _Fixture, client: MockAIAdapter) -> int:
    factory = create_worker_session_factory()
    try:
        runner = AIJobRunner(
            factory,
            worker_id="test-ai-worker",
            client=client,
            storage=InMemoryStorageFake(),
        )
        return await runner.run_pending(fixture.organization_id)
    finally:
        await factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_pending_job_reaches_provider_and_produces_observation() -> None:
    fixture = _Fixture()
    connection = await asyncpg.connect(_database_url())
    try:
        await _seed(connection, fixture)
    finally:
        await connection.close()
    try:
        output = {"observations": [{"code": TEST_OPTION_CODE, "description": "吃完了"}]}
        adapter = MockAIAdapter(result=output)

        processed = await _run_runner(fixture, adapter)

        assert processed == 1
        assert len(adapter.requests) == 1
        # Job 使用自己那一列記錄的版本，不是當下設定檔的版本。
        assert adapter.requests[0].model_version == "local-v1"

        job = await _job_row(fixture)
        assert job["status"] == "succeeded"
        assert job["claim_token"] is None
        assert job["claimed_by"] is None
        assert json.loads(job["raw_ai_output"]) == output

        assert await _report_status(fixture) == "succeeded"

        observations = await _observations(fixture)
        assert len(observations) == 1
        assert observations[0]["status"] == "succeeded"
        assert json.loads(observations[0]["validated_ai_observation"]) == output
        # 心得是唯一來源時，Observation 應追溯回那筆回報。
        assert observations[0]["source_type"] == "note"
        assert UUID(str(observations[0]["source_id"])) == fixture.report_id
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_provider_failure_releases_claim_for_retry() -> None:
    fixture = _Fixture()
    connection = await asyncpg.connect(_database_url())
    try:
        await _seed(connection, fixture)
    finally:
        await connection.close()
    try:
        processed = await _run_runner(fixture, MockAIAdapter(error=TimeoutError()))

        assert processed == 1
        job = await _job_row(fixture)
        # 供應商錯誤是暫時性的：Job 要回到佇列，而不是卡在 running。
        assert job["status"] == "retry_wait"
        assert job["claim_token"] is None
        assert job["retry_count"] == 1
        assert job["failure_reason"] == "TimeoutError"
        # 有退避才算重試：沒有它，三次重試會在同一輪內幾毫秒間燒完。
        assert job["available_at"] > datetime.now(timezone.utc)
        assert AI_MAX_RETRY >= 1
        # 這筆還會再試，對工作人員來說它仍在排隊。
        assert await _report_status(fixture) == "enqueued"
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_invalid_output_is_terminal_and_not_retried() -> None:
    fixture = _Fixture()
    connection = await asyncpg.connect(_database_url())
    try:
        await _seed(connection, fixture)
    finally:
        await connection.close()
    try:
        # 這個代碼不在收容所的有效選項裡，驗證一定失敗；重試不會改變結果。
        adapter = MockAIAdapter(result={"observations": [{"code": "feeding.not_registered"}]})

        await _run_runner(fixture, adapter)

        job = await _job_row(fixture)
        assert job["status"] == "failed"
        assert job["claim_token"] is None
        assert json.loads(job["validation_result"])["status"] == "invalid"

        observations = await _observations(fixture)
        assert len(observations) == 1
        assert observations[0]["status"] == "invalid"
        # 驗證失敗的內容不得晉升為正式觀察；JSON 欄位存的是 null。
        validated = observations[0]["validated_ai_observation"]
        assert validated is None or json.loads(validated) is None
    finally:
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_run_loop_starts_the_ai_iteration(monkeypatch: pytest.MonkeyPatch) -> None:
    """run() 只跑志工迴圈時，AI Job 永遠不會被處理——這正是原本的缺陷。"""
    started = asyncio.Event()

    async def fake_ai_iteration(factory, *, worker_id, client, storage=None) -> None:
        started.set()

    async def fake_volunteer_iteration(factory, *, worker_id) -> None:
        return None

    monkeypatch.setattr(worker, "run_ai_iteration", fake_ai_iteration)
    monkeypatch.setattr(worker, "run_volunteer_iteration", fake_volunteer_iteration)

    task = asyncio.create_task(worker.run())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
