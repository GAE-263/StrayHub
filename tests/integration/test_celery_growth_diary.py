from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
import services.api.app.api.line_webhook as line_webhook_module
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi import BackgroundTasks
from services.api.app.api.line_webhook import (
    _growth_diary_event_transaction,
    _handle_growth_diary_message,
)
from services.api.app.application.ai_job_dispatch import (
    create_growth_diary_analysis_job,
)
from services.api.app.application.celery_job_dispatch import (
    _payload,
    dispatch_ai_job,
    pending_celery_dispatches,
)
from services.api.app.application.growth_diary_ai_analysis_service import (
    GrowthDiaryAiAnalysisResult,
)
from services.api.app.application.growth_diary_job_service import (
    apply_growth_diary_result,
    claim_growth_diary_job,
    claim_growth_diary_notifications,
    mark_growth_diary_delivery,
    mark_growth_diary_retry,
)
from services.api.app.config.settings import get_settings, get_worker_settings
from services.api.app.infrastructure.ai.gemini_client import GeminiGrowthDiaryAnalysis
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.growth_diary import GrowthDiaryDraft, GrowthDiaryEntry
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    OrganizationMembership,
    User,
)
from services.api.app.persistence.repositories.adoption_draft_repository import (
    adoption_draft_token_digest,
)
from services.api.app.persistence.repositories.ai_job_repository import AIJobRepository
from services.worker.app.tasks import growth_diary as task_module
from services.worker.app.tasks.reconciliation import _publish
from sqlalchemy import select

from tests.integration.test_celery_adoption_suitability import _base_rows


def _database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


async def _seed_source(organization_id, adopter_id, animal_id, draft_id, inquiry_id) -> None:
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    now = datetime.now(timezone.utc)
    async with session_factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        session.add(
            AdoptionDraft(
                id=draft_id,
                opaque_token_digest=adoption_draft_token_digest(str(draft_id)),
                organization_id=organization_id,
                adopter_user_id=adopter_id,
                path="specific_animal",
                target_animal_id=animal_id,
                current_step="submitted",
                answers={},
                reconfirmation_keys=[],
                interaction_version=1,
                status="submitted",
                last_interaction_at=now,
                expires_at=now + timedelta(days=1),
            )
        )
        await session.flush()
        session.add(
            AdoptionInquiry(
                id=inquiry_id,
                organization_id=organization_id,
                draft_id=draft_id,
                adopter_user_id=adopter_id,
                path="specific_animal",
                target_animal_id=animal_id,
                animal_name_snapshot="小福",
                shelter_number_snapshot="C-001",
                answers={},
                adopter_name="王小明",
                phone_number="0911222333",
                status="submitted",
                submitted_at=now,
            )
        )


async def _create_job(
    organization_id,
    adopter_id,
    animal_id,
    inquiry_id,
    *,
    note: str | None = "今天精神穩定",
    photo_keys: list[str] | None = None,
):
    keys = list(photo_keys or [])
    async with session_factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        entry = GrowthDiaryEntry(
            organization_id=organization_id,
            inquiry_id=inquiry_id,
            animal_id=animal_id,
            adopter_user_id=adopter_id,
            note=note,
            photo_key=keys[-1] if keys else None,
            photo_keys=keys,
            photo_content_type="image/webp" if keys else None,
            entry_date=date.today(),
            content_version=1,
            ai_analysis_status="pending",
        )
        session.add(entry)
        await session.flush()
        job = await create_growth_diary_analysis_job(
            AIJobRepository(session, organization_id),
            entry_id=entry.id,
            content_version=entry.content_version,
            photo_keys=keys,
        )
        return entry.id, job.id


async def _setup(*, note="今天精神穩定", photo_keys=None):
    organization_id, adopter_id, animal_id = uuid4(), uuid4(), uuid4()
    draft_id, inquiry_id = uuid4(), uuid4()
    await _seed_source(organization_id, adopter_id, animal_id, draft_id, inquiry_id)
    entry_id, job_id = await _create_job(
        organization_id,
        adopter_id,
        animal_id,
        inquiry_id,
        note=note,
        photo_keys=photo_keys,
    )
    return organization_id, adopter_id, animal_id, draft_id, inquiry_id, entry_id, job_id


async def _cleanup(organization_id) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        user_rows = await connection.fetch(
            "SELECT adopter_user_id AS user_id FROM adoption_inquiries "
            "WHERE organization_id = $1 UNION SELECT user_id FROM organization_memberships "
            "WHERE organization_id = $1",
            organization_id,
        )
        user_ids = [row["user_id"] for row in user_rows]
        await connection.execute(
            "DELETE FROM ai_processing_jobs WHERE organization_id = $1", organization_id
        )
        await connection.execute(
            "DELETE FROM growth_diary_drafts WHERE organization_id = $1", organization_id
        )
        await connection.execute(
            "DELETE FROM growth_diary_entries WHERE organization_id = $1", organization_id
        )
        if user_ids:
            await connection.execute(
                "DELETE FROM line_user_bindings WHERE user_id = ANY($1::uuid[])", user_ids
            )
        await connection.execute(
            "DELETE FROM organization_memberships WHERE organization_id = $1", organization_id
        )
        await connection.execute(
            "DELETE FROM adoption_inquiries WHERE organization_id = $1", organization_id
        )
        await connection.execute(
            "DELETE FROM adoption_drafts WHERE organization_id = $1", organization_id
        )
        await connection.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        if user_ids:
            await connection.execute("DELETE FROM users WHERE id = ANY($1::uuid[])", user_ids)
        await connection.execute("DELETE FROM organizations WHERE id = $1", organization_id)
    finally:
        await connection.close()


def _result(mood: str = "neutral") -> GrowthDiaryAiAnalysisResult:
    return GrowthDiaryAiAnalysisResult(
        mood=mood,
        adopter_reply="已收到你的分享，若持續異常請聯繫獸醫。",
        staff_summary="活動與食慾需要持續觀察。",
        provider="google_gemini",
        model_name="gemini-test",
        model_version="gemini-test",
        prompt_version="growth-diary-v2-multimodal",
        output_schema_version="growth-diary-analysis-v1",
        raw_output='{"mood":"neutral"}',
    )


@pytest.mark.asyncio
async def test_growth_diary_job_snapshot_and_payload_are_minimal() -> None:
    values = await _setup(photo_keys=["growth-diary/safe.webp"])
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    try:
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, job_id)
            assert job is not None
            assert job.input_snapshot == {
                "content_version": 1,
                "photo_keys": ["growth-diary/safe.webp"],
                "schema_version": "1",
                "source": "growth_diary_entry",
            }
            assert _payload(job) == {
                "job_id": str(job_id),
                "resource_id": str(entry_id),
                "organization_id": str(organization_id),
                "expected_version": 1,
            }
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_growth_diary_success_is_conditional_and_idempotent() -> None:
    values = await _setup()
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    try:
        snapshot = await claim_growth_diary_job(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="worker-a",
            worker_name="worker-a",
        )
        assert snapshot is not None and snapshot.note == "今天精神穩定"
        outcome = await apply_growth_diary_result(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="worker-a",
            result=_result(),
        )
        assert outcome.applied is True
        duplicate = await apply_growth_diary_result(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="worker-a",
            result=_result("concern"),
        )
        assert duplicate.applied is False
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.get(GrowthDiaryEntry, entry_id)
            assert entry is not None
            assert entry.ai_analysis_status == "succeeded"
            assert entry.ai_mood == "neutral"
            assert entry.note == "今天精神穩定"
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("update_kind", ["note", "photo"])
async def test_growth_diary_old_result_is_discarded_after_content_update(update_kind: str) -> None:
    values = await _setup()
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    try:
        assert await claim_growth_diary_job(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="stale",
            worker_name="worker-a",
        )
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.get(GrowthDiaryEntry, entry_id)
            assert entry is not None
            if update_kind == "note":
                entry.note = "更新後內容"
            else:
                entry.photo_key = "growth-diary/new.webp"
                entry.photo_keys = ["growth-diary/new.webp"]
                entry.photo_content_type = "image/webp"
            entry.content_version += 1
            entry.ai_analysis_status = "pending"
        outcome = await apply_growth_diary_result(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="stale",
            result=_result("concern"),
        )
        assert outcome.stale is True
        assert (
            await claim_growth_diary_notifications(
                session_factory,
                job_id=job_id,
                entry_id=entry_id,
                organization_id=organization_id,
                expected_version=1,
                claim_token="notification",
            )
            == ()
        )
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_growth_diary_newest_job_is_the_only_result_applied() -> None:
    values = await _setup()
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, old_job_id = values
    try:
        assert await claim_growth_diary_job(
            session_factory,
            job_id=old_job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="old-worker",
            worker_name="old-worker",
        )
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.get(GrowthDiaryEntry, entry_id)
            assert entry is not None
            entry.note = "第二版內容"
            entry.content_version = 2
            entry.ai_analysis_status = "pending"
            entry.ai_content_version = None
            new_job = await create_growth_diary_analysis_job(
                AIJobRepository(session, organization_id),
                entry_id=entry_id,
                content_version=2,
                photo_keys=[],
            )
            new_job_id = new_job.id

        old_outcome = await apply_growth_diary_result(
            session_factory,
            job_id=old_job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="old-worker",
            result=_result("concern"),
        )
        assert old_outcome.stale is True
        newest_snapshot = await claim_growth_diary_job(
            session_factory,
            job_id=new_job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=2,
            claim_token="new-worker",
            worker_name="new-worker",
        )
        assert newest_snapshot is not None and newest_snapshot.note == "第二版內容"
        assert (
            await apply_growth_diary_result(
                session_factory,
                job_id=new_job_id,
                entry_id=entry_id,
                organization_id=organization_id,
                expected_version=2,
                claim_token="new-worker",
                result=_result("positive"),
            )
        ).applied

        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.get(GrowthDiaryEntry, entry_id)
            old_job = await session.get(AIProcessingJob, old_job_id)
            new_job = await session.get(AIProcessingJob, new_job_id)
            assert entry is not None and old_job is not None and new_job is not None
            assert entry.content_version == entry.ai_content_version == 2
            assert entry.ai_mood == "positive"
            assert old_job.status == "discarded"
            assert new_job.status == "succeeded"
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_growth_diary_failure_preserves_authoritative_content() -> None:
    values = await _setup(photo_keys=["growth-diary/original.webp"])
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    try:
        assert await claim_growth_diary_job(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="failure",
            worker_name="worker-a",
        )
        assert (
            await apply_growth_diary_result(
                session_factory,
                job_id=job_id,
                entry_id=entry_id,
                organization_id=organization_id,
                expected_version=1,
                claim_token="failure",
                result=None,
                failure_reason="permanent:MalformedAiResponse",
            )
        ).applied
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.get(GrowthDiaryEntry, entry_id)
            job = await session.get(AIProcessingJob, job_id)
            assert entry is not None and job is not None
            assert entry.note == "今天精神穩定"
            assert entry.photo_keys == ["growth-diary/original.webp"]
            assert entry.ai_analysis_status == "failed"
            assert entry.ai_mood is None
            assert job.status == "failed"
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_growth_diary_duplicate_claim_retry_and_stale_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await _setup()
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    monkeypatch.setattr(get_worker_settings(), "celery_visibility_timeout", 1)
    monkeypatch.setattr(get_worker_settings(), "celery_max_retries", 2)
    try:

        async def claim(token: str):
            return await claim_growth_diary_job(
                session_factory,
                job_id=job_id,
                entry_id=entry_id,
                organization_id=organization_id,
                expected_version=1,
                claim_token=token,
                worker_name=token,
            )

        claims = await asyncio.gather(claim("worker-a"), claim("worker-b"))
        assert sum(item is not None for item in claims) == 1
        winner = "worker-a" if claims[0] else "worker-b"
        first = claims[0] or claims[1]
        await mark_growth_diary_retry(
            session_factory,
            job_id=job_id,
            organization_id=organization_id,
            claim_token=winner,
            failure_reason="TransientAiError",
            countdown=0,
        )
        retried = await claim("worker-c")
        assert retried is not None and first is not None
        assert (retried.note, retried.photo_key) == (first.note, first.photo_key)
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, job_id)
            assert job is not None
            job.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=2)
        recovered = await claim("worker-d")
        assert recovered is not None and recovered.skip_ai_reason == "lease_retry_exhausted"
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_growth_diary_forged_tenant_cannot_claim() -> None:
    values = await _setup()
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    try:
        assert (
            await claim_growth_diary_job(
                session_factory,
                job_id=job_id,
                entry_id=entry_id,
                organization_id=uuid4(),
                expected_version=1,
                claim_token="forged",
                worker_name="attacker",
            )
            is None
        )
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_growth_diary_concern_fanout_is_tenant_scoped_and_retryable() -> None:
    values = await _setup()
    organization_id, adopter_id, _animal, _draft, _inquiry, entry_id, job_id = values
    staff_a, staff_b = uuid4(), uuid4()
    try:
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            session.add_all(
                [
                    User(id=staff_a, username=f"gd-{staff_a}", display_name="A", status="active"),
                    User(id=staff_b, username=f"gd-{staff_b}", display_name="B", status="active"),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    OrganizationMembership(
                        organization_id=organization_id,
                        user_id=staff_a,
                        role="STAFF",
                        status="active",
                    ),
                    OrganizationMembership(
                        organization_id=organization_id,
                        user_id=staff_b,
                        role="SHELTER_ADMIN",
                        status="active",
                    ),
                    LineUserBinding(
                        line_user_id=f"U{adopter_id.hex}", user_id=adopter_id, status="active"
                    ),
                    LineUserBinding(
                        line_user_id=f"U{staff_a.hex}", user_id=staff_a, status="active"
                    ),
                    LineUserBinding(
                        line_user_id=f"U{staff_b.hex}", user_id=staff_b, status="active"
                    ),
                ]
            )
        assert await claim_growth_diary_job(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="analysis",
            worker_name="worker-a",
        )
        assert (
            await apply_growth_diary_result(
                session_factory,
                job_id=job_id,
                entry_id=entry_id,
                organization_id=organization_id,
                expected_version=1,
                claim_token="analysis",
                result=_result("concern"),
            )
        ).applied
        deliveries = await claim_growth_diary_notifications(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="notify-a",
        )
        assert {item.user_id for item in deliveries} == {adopter_id, staff_a, staff_b}
        first, second, third = deliveries
        await mark_growth_diary_delivery(
            session_factory,
            job_id=job_id,
            organization_id=organization_id,
            delivery_id=first.delivery_id,
            claim_token="notify-a",
            status="sent",
        )
        await mark_growth_diary_delivery(
            session_factory,
            job_id=job_id,
            organization_id=organization_id,
            delivery_id=second.delivery_id,
            claim_token="notify-a",
            status="retry_wait",
            countdown=0,
        )
        await mark_growth_diary_delivery(
            session_factory,
            job_id=job_id,
            organization_id=organization_id,
            delivery_id=third.delivery_id,
            claim_token="notify-a",
            status="sent",
        )
        assert (job_id, organization_id) in await pending_celery_dispatches(session_factory)
        retry = await claim_growth_diary_notifications(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="notify-b",
        )
        assert [item.delivery_id for item in retry] == [second.delivery_id]
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending_enqueue", "enqueue_failed", "retry_wait", "running"])
async def test_growth_diary_reconciliation_recovers_execution_states(status: str) -> None:
    values = await _setup()
    organization_id, _adopter, _animal, _draft, _inquiry, _entry_id, job_id = values
    try:
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, job_id)
            assert job is not None
            job.status = status
            job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            if status == "running":
                job.claimed_at = datetime.now(timezone.utc) - timedelta(days=1)
        assert (job_id, organization_id) in await pending_celery_dispatches(session_factory)
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_production_disabled_saves_entry_without_ai_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, adopter_id, animal_id, draft_id, inquiry_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    await _seed_source(organization_id, adopter_id, animal_id, draft_id, inquiry_id)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", False)
    tasks, line = BackgroundTasks(), MockLineAdapter()
    try:
        async with session_factory() as session:
            async with _growth_diary_event_transaction(
                session,
                event_id="growth-disabled",
                background_tasks=tasks,
            ) as boundary:
                await set_organization_scope(session, organization_id)
                pending = GrowthDiaryDraft(
                    adopter_user_id=adopter_id,
                    organization_id=organization_id,
                    inquiry_id=inquiry_id,
                    animal_id=animal_id,
                )
                session.add(pending)
                await session.flush()
                await _handle_growth_diary_message(
                    session,
                    line,
                    {
                        "webhookEventId": "growth-disabled",
                        "replyToken": "reply",
                        "source": {"userId": "U-disabled"},
                        "message": {"type": "text", "text": "今天一切正常"},
                    },
                    adopter_user_id=adopter_id,
                    pending_draft=pending,
                    event_boundary=boundary,
                )
        assert tasks.tasks == []
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.scalar(
                select(GrowthDiaryEntry).where(GrowthDiaryEntry.organization_id == organization_id)
            )
            assert entry is not None
            assert entry.note == "今天一切正常"
            assert entry.ai_analysis_status == "unconfigured"
            assert (
                await session.scalar(
                    select(AIProcessingJob.id).where(
                        AIProcessingJob.organization_id == organization_id
                    )
                )
                is None
            )
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_growth_diary_entry_and_job_commit_before_dispatch_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, adopter_id, animal_id, draft_id, inquiry_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    await _seed_source(organization_id, adopter_id, animal_id, draft_id, inquiry_id)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", True)
    tasks, line = BackgroundTasks(), MockLineAdapter()
    try:
        async with session_factory() as session:
            async with _growth_diary_event_transaction(
                session,
                event_id="growth-celery",
                background_tasks=tasks,
            ) as boundary:
                await set_organization_scope(session, organization_id)
                pending = GrowthDiaryDraft(
                    adopter_user_id=adopter_id,
                    organization_id=organization_id,
                    inquiry_id=inquiry_id,
                    animal_id=animal_id,
                )
                session.add(pending)
                await session.flush()
                await _handle_growth_diary_message(
                    session,
                    line,
                    {
                        "webhookEventId": "growth-celery",
                        "replyToken": "reply",
                        "source": {"userId": "U-celery"},
                        "message": {"type": "text", "text": "今天很有精神"},
                    },
                    adopter_user_id=adopter_id,
                    pending_draft=pending,
                    event_boundary=boundary,
                )
        assert len(tasks.tasks) == 1
        assert tasks.tasks[0].func is dispatch_ai_job
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.scalar(
                select(GrowthDiaryEntry).where(GrowthDiaryEntry.organization_id == organization_id)
            )
            job = await session.scalar(
                select(AIProcessingJob).where(AIProcessingJob.organization_id == organization_id)
            )
            assert entry is not None and job is not None
            assert entry.note == "今天很有精神"
            assert job.target_id == entry.id
            assert job.domain_version == entry.content_version == 1
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_storage_failure_classification_and_text_only_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimeoutStorage:
        async def get_with_content_type(self, **_kwargs):
            raise EndpointConnectionError(endpoint_url="http://storage")

    class MissingStorage:
        async def get_with_content_type(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "GetObject",
            )

    class ServerStorage:
        async def get_with_content_type(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {"Code": "ServiceUnavailable"},
                    "ResponseMetadata": {"HTTPStatusCode": 503},
                },
                "GetObject",
            )

    class InvalidStorage:
        async def get_with_content_type(self, **_kwargs):
            return b"not-webp", "image/png"

    monkeypatch.setattr(task_module, "MinioStorageAdapter", TimeoutStorage)
    with pytest.raises(task_module.TransientStorageError):
        await task_module.fetch_growth_diary_photo(
            organization_id=uuid4(), key="growth-diary/photo.webp"
        )
    monkeypatch.setattr(task_module, "MinioStorageAdapter", MissingStorage)
    with pytest.raises(task_module.PermanentStorageError):
        await task_module.fetch_growth_diary_photo(
            organization_id=uuid4(), key="growth-diary/photo.webp"
        )
    monkeypatch.setattr(task_module, "MinioStorageAdapter", ServerStorage)
    with pytest.raises(task_module.TransientStorageError):
        await task_module.fetch_growth_diary_photo(
            organization_id=uuid4(), key="growth-diary/photo.webp"
        )
    monkeypatch.setattr(task_module, "MinioStorageAdapter", InvalidStorage)
    with pytest.raises(task_module.PermanentStorageError):
        await task_module.fetch_growth_diary_photo(
            organization_id=uuid4(), key="growth-diary/photo.webp"
        )


@pytest.mark.asyncio
async def test_growth_diary_storage_read_is_organization_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    observed: dict[str, object] = {}

    class CapturingStorage:
        async def get_with_content_type(self, *, scope, key):
            observed["organization_id"] = scope.organization_id
            observed["key"] = key
            return b"webp", "image/webp"

    monkeypatch.setattr(task_module, "MinioStorageAdapter", CapturingStorage)
    assert await task_module.fetch_growth_diary_photo(
        organization_id=organization_id,
        key="growth-diary/scoped.webp",
    ) == (b"webp", "image/webp")
    assert observed == {
        "organization_id": organization_id,
        "key": "growth-diary/scoped.webp",
    }


@pytest.mark.asyncio
async def test_growth_diary_publish_failure_preserves_entry_and_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await _setup()
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    try:

        def fail_publish(*_args, **_kwargs):
            raise ConnectionError("redis unavailable")

        monkeypatch.setattr(celery_app, "send_task", fail_publish)
        assert await dispatch_ai_job(job_id, organization_id) is False
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.get(GrowthDiaryEntry, entry_id)
            job = await session.get(AIProcessingJob, job_id)
            assert entry is not None and entry.note == "今天精神穩定"
            assert job is not None and job.status == "enqueue_failed"
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_failed_growth_diary_notification_is_republished_by_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await _setup()
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    published: list[dict] = []
    try:
        assert await claim_growth_diary_job(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="failed-analysis",
            worker_name="worker-a",
        )
        assert (
            await apply_growth_diary_result(
                session_factory,
                job_id=job_id,
                entry_id=entry_id,
                organization_id=organization_id,
                expected_version=1,
                claim_token="failed-analysis",
                result=None,
                failure_reason="permanent:MalformedAiResponse",
            )
        ).applied
        monkeypatch.setattr(
            celery_app,
            "send_task",
            lambda *_args, **kwargs: (
                published.append(kwargs) or type("Result", (), {"id": str(job_id)})()
            ),
        )

        assert (job_id, organization_id) in await pending_celery_dispatches(session_factory)
        assert await _publish(
            session_factory,
            job_id=job_id,
            organization_id=organization_id,
        )
        assert len(published) == 1
        assert published[0]["task_id"] == str(job_id)
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_post_commit_redelivery_notifies_without_rerunning_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await _setup()
    organization_id, adopter_id, _animal, _draft, _inquiry, entry_id, job_id = values
    pushed: list[str] = []
    try:
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            session.add(
                LineUserBinding(
                    line_user_id=f"U{adopter_id.hex}",
                    user_id=adopter_id,
                    status="active",
                )
            )
        assert await claim_growth_diary_job(
            session_factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=1,
            claim_token="committed",
            worker_name="worker-a",
        )
        assert (
            await apply_growth_diary_result(
                session_factory,
                job_id=job_id,
                entry_id=entry_id,
                organization_id=organization_id,
                expected_version=1,
                claim_token="committed",
                result=_result(),
            )
        ).applied

        class GeminiMustNotRun:
            def __init__(self, *_args, **_kwargs):
                raise AssertionError("Gemini must not rerun after domain commit")

        async def record_push(**kwargs):
            pushed.append(kwargs["delivery"].delivery_id)

        monkeypatch.setattr(task_module, "GeminiClient", GeminiMustNotRun)
        monkeypatch.setattr(task_module, "_push_delivery", record_push)
        kwargs = {
            "job_id": str(job_id),
            "resource_id": str(entry_id),
            "organization_id": str(organization_id),
            "expected_version": 1,
        }
        assert (
            await asyncio.to_thread(
                lambda: task_module.analyze_entry.apply(kwargs=kwargs, task_id=str(job_id)).get()
            )
            == "succeeded"
        )
        assert (
            await asyncio.to_thread(
                lambda: task_module.analyze_entry.apply(kwargs=kwargs, task_id=str(job_id)).get()
            )
            == "discarded_or_duplicate"
        )
        assert pushed == [f"adopter:{adopter_id}"]
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_missing_photo_with_text_runs_text_only_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await _setup(photo_keys=["growth-diary/missing.webp"])
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values
    calls: list[tuple[bytes | None, str | None]] = []

    class FakeGemini:
        model_name = "gemini-test"

        def __init__(self, *_args, **_kwargs):
            pass

        async def analyze_growth_diary_entry_strict(
            self, _prompt, *, image=None, image_mime_type=None
        ):
            calls.append((image, image_mime_type))
            return GeminiGrowthDiaryAnalysis(
                mood="neutral",
                adopter_reply="已收到你的分享。",
                staff_summary="文字紀錄未見明確異常。",
                raw_output='{"mood":"neutral"}',
            )

        async def aclose(self):
            return None

    async def missing_photo(**_kwargs):
        raise task_module.PermanentStorageError("NoSuchKey")

    settings = get_worker_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(task_module, "GeminiClient", FakeGemini)
    monkeypatch.setattr(task_module, "fetch_growth_diary_photo", missing_photo)
    try:
        kwargs = {
            "job_id": str(job_id),
            "resource_id": str(entry_id),
            "organization_id": str(organization_id),
            "expected_version": 1,
        }
        await asyncio.to_thread(
            lambda: task_module.analyze_entry.apply(kwargs=kwargs, task_id=str(job_id)).get()
        )
        assert calls == [(None, None)]
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.get(GrowthDiaryEntry, entry_id)
            assert entry is not None
            assert entry.ai_analysis_status == "succeeded"
            assert entry.photo_keys == ["growth-diary/missing.webp"]
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
async def test_photo_only_missing_object_finishes_failed_without_deleting_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = await _setup(note=None, photo_keys=["growth-diary/missing.webp"])
    organization_id, _adopter, _animal, _draft, _inquiry, entry_id, job_id = values

    class GeminiMustNotRun:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("photo-only missing object must not call Gemini")

    async def missing_photo(**_kwargs):
        raise task_module.PermanentStorageError("NoSuchKey")

    monkeypatch.setattr(get_worker_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(task_module, "GeminiClient", GeminiMustNotRun)
    monkeypatch.setattr(task_module, "fetch_growth_diary_photo", missing_photo)
    try:
        kwargs = {
            "job_id": str(job_id),
            "resource_id": str(entry_id),
            "organization_id": str(organization_id),
            "expected_version": 1,
        }
        await asyncio.to_thread(
            lambda: task_module.analyze_entry.apply(kwargs=kwargs, task_id=str(job_id)).get()
        )
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.get(GrowthDiaryEntry, entry_id)
            assert entry is not None
            assert entry.ai_analysis_status == "failed"
            assert entry.photo_keys == ["growth-diary/missing.webp"]
    finally:
        await _cleanup(organization_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("instant", "timezone_name", "expected"),
    [
        (
            datetime(2026, 9, 7, 16, 30, tzinfo=timezone.utc),
            "Asia/Taipei",
            date(2026, 9, 8),
        ),
        (
            datetime(2026, 11, 1, 3, 30, tzinfo=timezone.utc),
            "America/New_York",
            date(2026, 10, 31),
        ),
    ],
)
async def test_growth_diary_entry_date_remains_organization_local_across_dst(
    monkeypatch: pytest.MonkeyPatch,
    instant: datetime,
    timezone_name: str,
    expected: date,
) -> None:
    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz or timezone.utc)

    class Session:
        async def get(self, _model, _organization_id):
            return type("Organization", (), {"timezone": timezone_name})()

    monkeypatch.setattr(line_webhook_module, "datetime", FrozenDateTime)

    assert await line_webhook_module._organization_today(Session(), uuid4()) == expected
