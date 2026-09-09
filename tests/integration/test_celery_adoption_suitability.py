from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
import services.worker.app.tasks.adoption as adoption_task_module
from services.api.app.application.adoption_suitability_job_service import (
    apply_suitability_result,
    claim_suitability_job,
    mark_suitability_retry,
)
from services.api.app.application.celery_job_dispatch import (
    dispatch_ai_job,
    pending_celery_dispatches,
)
from services.api.app.application.line_adoption_conversation import (
    LineAdoptionConversationService,
)
from services.api.app.config.settings import get_settings, get_worker_settings
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.infrastructure.ai.gemini_client import GeminiSuitabilityResult
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
    adoption_draft_token_digest,
)
from services.worker.app.persistence.job_repository import WorkerJobRepository
from services.worker.app.tasks.adoption import analyze_suitability
from services.worker.app.tasks.reconciliation import _publish
from sqlalchemy import select


def _database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


async def _base_rows(organization_id, adopter_id, animal_id) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Celery Test Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"CELERY-{organization_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Celery Test Adopter', 'active', now(), now())
            """,
            adopter_id,
            f"celery-{adopter_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, is_adoptable,
                 created_at, updated_at)
            VALUES ($1, $2, '小福', 'C-001', 'active', true, now(), now())
            """,
            animal_id,
            organization_id,
        )
    finally:
        await connection.close()


async def _cleanup(organization_id, adopter_id) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("DELETE FROM line_user_bindings WHERE user_id = $1", adopter_id)
        await connection.execute(
            "DELETE FROM ai_processing_jobs WHERE organization_id = $1", organization_id
        )
        await connection.execute(
            "DELETE FROM adoption_drafts WHERE organization_id = $1", organization_id
        )
        await connection.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        await connection.execute("DELETE FROM users WHERE id = $1", adopter_id)
        await connection.execute("DELETE FROM organizations WHERE id = $1", organization_id)
    finally:
        await connection.close()


async def _add_line_binding(adopter_id, line_user_id: str) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            """
            INSERT INTO line_user_bindings
                (id, line_user_id, user_id, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', now(), now())
            """,
            uuid4(),
            line_user_id,
            adopter_id,
        )
    finally:
        await connection.close()


async def _create_waiting_job(
    organization_id, adopter_id, animal_id, draft_id, job_id, *, version: int = 4
) -> None:
    async with session_factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            now = datetime.now(timezone.utc)
            session.add_all(
                [
                    AdoptionDraft(
                        id=draft_id,
                        opaque_token_digest=adoption_draft_token_digest(str(draft_id)),
                        organization_id=organization_id,
                        adopter_user_id=adopter_id,
                        path="specific_animal",
                        target_animal_id=animal_id,
                        current_step=AdoptionDraftState.AWAITING_AI_SUITABILITY.value,
                        answers={
                            "housing_type": "house",
                            "dog_experience": "first_time",
                            "other_pets": "none",
                            "household_members": "adults_only",
                            "work_schedule": "work_from_home",
                            "parenting_style": "structured",
                            "patience_level": "high_patience",
                            "adoption_motivation": "companionship",
                        },
                        reconfirmation_keys=[],
                        interaction_version=version,
                        status="active",
                        last_interaction_at=now,
                        expires_at=now + timedelta(hours=1),
                    ),
                    AIProcessingJob(
                        id=job_id,
                        organization_id=organization_id,
                        job_type="adoption_suitability",
                        target_type="adoption_draft",
                        target_id=draft_id,
                        domain_version=version,
                        execution_backend="celery",
                        provider="google_gemini",
                        model_name="gemini-test",
                        model_version="gemini-test",
                        prompt_template_id="adoption-suitability",
                        prompt_version="1",
                        output_schema_version="1",
                        status="queued",
                        retry_count=0,
                    ),
                ]
            )


@pytest.mark.asyncio
async def test_suitability_job_is_transactional_tenant_scoped_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, other_organization_id = uuid4(), uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    token = "celery-adoption-test-token"
    await engine.dispose(close=False)
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", True)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                session.add(
                    AdoptionDraft(
                        id=draft_id,
                        opaque_token_digest=adoption_draft_token_digest(token),
                        organization_id=organization_id,
                        adopter_user_id=adopter_id,
                        path="specific_animal",
                        target_animal_id=animal_id,
                        current_step=AdoptionDraftState.CONFIRMING_ANSWERS.value,
                        answers={
                            "housing_type": "house",
                            "dog_experience": "first_time",
                            "other_pets": "none",
                            "household_members": "adults_only",
                            "work_schedule": "work_from_home",
                            "parenting_style": "structured",
                            "patience_level": "high_patience",
                            "adoption_motivation": "companionship",
                        },
                        reconfirmation_keys=[],
                        interaction_version=8,
                        status="active",
                        last_interaction_at=datetime.now(timezone.utc),
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    )
                )
                await session.flush()
                result = await LineAdoptionConversationService(
                    AdoptionDraftRepository(session, organization_id)
                ).handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_answers",
                    value=None,
                    event_id="confirm-for-celery",
                )
                assert result.state == AdoptionDraftState.AWAITING_AI_SUITABILITY
                assert result.ai_job_id is not None
                assert result.ai_job_version == 9
                job = await session.scalar(
                    select(AIProcessingJob).where(
                        AIProcessingJob.id == result.ai_job_id,
                        AIProcessingJob.organization_id == organization_id,
                    )
                )
                assert job is not None
                assert job.status == "pending_enqueue"
                assert job.domain_version == 9
                assert job.execution_backend == "celery"

        def fail_publish(*_args, **_kwargs):
            raise ConnectionError("redis unavailable")

        monkeypatch.setattr(celery_app, "send_task", fail_publish)
        assert (
            await dispatch_ai_job(result.ai_job_id, organization_id, factory=session_factory)
            is False
        )
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                failed_job = await session.scalar(
                    select(AIProcessingJob).where(
                        AIProcessingJob.id == result.ai_job_id,
                        AIProcessingJob.organization_id == organization_id,
                    )
                )
                assert failed_job is not None and failed_job.status == "enqueue_failed"

        monkeypatch.setattr(
            celery_app,
            "send_task",
            lambda *_args, **_kwargs: SimpleNamespace(id=str(result.ai_job_id)),
        )
        assert (
            await dispatch_ai_job(result.ai_job_id, organization_id, factory=session_factory)
            is True
        )

        assert (
            await claim_suitability_job(
                session_factory,
                job_id=result.ai_job_id,
                draft_id=draft_id,
                organization_id=other_organization_id,
                expected_version=9,
                claim_token="wrong-tenant",
                worker_name="test-worker",
            )
            is None
        )
        snapshot = await claim_suitability_job(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=9,
            claim_token="claim-1",
            worker_name="test-worker",
        )
        assert snapshot is not None
        outcome = await apply_suitability_result(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=9,
            claim_token="claim-1",
            snapshot=snapshot,
            result=GeminiSuitabilityResult(score=82, explanation="生活型態相當合適。"),
        )
        assert outcome.applied is True
        duplicate = await apply_suitability_result(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=9,
            claim_token="claim-1",
            snapshot=snapshot,
            result=GeminiSuitabilityResult(score=1, explanation="不應覆寫"),
        )
        assert duplicate.applied is False

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                draft = await session.scalar(
                    select(AdoptionDraft).where(
                        AdoptionDraft.id == draft_id,
                        AdoptionDraft.organization_id == organization_id,
                    )
                )
                assert draft is not None
                assert draft.ai_suitability_score == 82
                assert draft.interaction_version == 10
                assert draft.current_step == AdoptionDraftState.AWAITING_ADOPTER_NAME.value
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_suitability_result_is_discarded_after_newer_domain_state() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                now = datetime.now(timezone.utc)
                session.add_all(
                    [
                        AdoptionDraft(
                            id=draft_id,
                            opaque_token_digest=adoption_draft_token_digest(str(draft_id)),
                            organization_id=organization_id,
                            adopter_user_id=adopter_id,
                            path="specific_animal",
                            target_animal_id=animal_id,
                            current_step=AdoptionDraftState.AWAITING_AI_SUITABILITY.value,
                            answers={"housing_type": "house"},
                            reconfirmation_keys=[],
                            interaction_version=4,
                            status="active",
                            last_interaction_at=now,
                            expires_at=now + timedelta(hours=1),
                        ),
                        AIProcessingJob(
                            id=job_id,
                            organization_id=organization_id,
                            job_type="adoption_suitability",
                            target_type="adoption_draft",
                            target_id=draft_id,
                            domain_version=4,
                            execution_backend="celery",
                            provider="google_gemini",
                            model_name="gemini-test",
                            model_version="gemini-test",
                            prompt_template_id="adoption-suitability",
                            prompt_version="1",
                            output_schema_version="1",
                            status="queued",
                            retry_count=0,
                        ),
                    ]
                )

        snapshot = await claim_suitability_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="claim-before-user-input",
            worker_name="test-worker",
        )
        assert snapshot is not None

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                draft = await session.scalar(
                    select(AdoptionDraft)
                    .where(
                        AdoptionDraft.id == draft_id,
                        AdoptionDraft.organization_id == organization_id,
                    )
                    .with_for_update()
                )
                assert draft is not None
                draft.current_step = AdoptionDraftState.CONFIRMING_ANSWERS.value
                draft.interaction_version += 1

        outcome = await apply_suitability_result(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="claim-before-user-input",
            snapshot=snapshot,
            result=GeminiSuitabilityResult(score=99, explanation="過期結果"),
        )
        assert outcome.applied is False
        assert outcome.stale is True

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                job = await session.scalar(
                    select(AIProcessingJob).where(
                        AIProcessingJob.id == job_id,
                        AIProcessingJob.organization_id == organization_id,
                    )
                )
                draft = await session.scalar(
                    select(AdoptionDraft).where(
                        AdoptionDraft.id == draft_id,
                        AdoptionDraft.organization_id == organization_id,
                    )
                )
                assert job is not None and job.status == "discarded"
                assert draft is not None and draft.ai_suitability_score is None
                assert draft.interaction_version == 5
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_only_one_worker_can_claim_the_same_suitability_job() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)

        async def claim(token: str):
            return await claim_suitability_job(
                session_factory,
                job_id=job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=4,
                claim_token=token,
                worker_name=token,
            )

        claims = await asyncio.gather(claim("worker-a"), claim("worker-b"))

        assert sum(item is not None for item in claims) == 1
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_action", "expected_state", "expected_status"),
    [
        ("cancel", AdoptionDraftState.CANCELLED, "cancelled"),
        ("back", AdoptionDraftState.CONFIRMING_ANSWERS, "active"),
    ],
)
async def test_user_transition_wins_while_suitability_is_in_flight(
    user_action: str,
    expected_state: AdoptionDraftState,
    expected_status: str,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    token = str(draft_id)
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        snapshot = await claim_suitability_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="blocked-in-gemini",
            worker_name="worker-a",
        )
        assert snapshot is not None

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                transition = await LineAdoptionConversationService(
                    AdoptionDraftRepository(session, organization_id)
                ).handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action=user_action,
                    value=None,
                    event_id=f"race-{user_action}",
                )
                assert transition.state == expected_state

        stale = await apply_suitability_result(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="blocked-in-gemini",
            snapshot=snapshot,
            result=GeminiSuitabilityResult(score=99, explanation="過期結果"),
        )
        assert stale.applied is False
        assert stale.stale is True
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                draft = await session.scalar(
                    select(AdoptionDraft).where(AdoptionDraft.id == draft_id)
                )
                job = await session.scalar(
                    select(AIProcessingJob).where(AIProcessingJob.id == job_id)
                )
                assert draft is not None and job is not None
                assert draft.current_step == expected_state.value
                assert draft.status == expected_status
                assert draft.interaction_version == 5
                assert draft.ai_suitability_score is None
                assert job.status == "discarded"
                assert (job.validation_result or {}).get("notification_status") is None
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_newer_suitability_job_remains_authoritative_over_old_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, old_job_id = uuid4(), uuid4(), uuid4(), uuid4()
    token = str(draft_id)
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", True)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, old_job_id)
        old_snapshot = await claim_suitability_job(
            session_factory,
            job_id=old_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="old-worker",
            worker_name="worker-a",
        )
        assert old_snapshot is not None
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                service = LineAdoptionConversationService(
                    AdoptionDraftRepository(session, organization_id)
                )
                back = await service.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="back",
                    value=None,
                    event_id="new-input-back",
                )
                assert back.state == AdoptionDraftState.CONFIRMING_ANSWERS
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                latest = await LineAdoptionConversationService(
                    AdoptionDraftRepository(session, organization_id)
                ).handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_answers",
                    value=None,
                    event_id="new-input-confirm",
                )
                assert latest.ai_job_id is not None
                assert latest.ai_job_version == 6

        old_outcome = await apply_suitability_result(
            session_factory,
            job_id=old_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="old-worker",
            snapshot=old_snapshot,
            result=GeminiSuitabilityResult(score=5, explanation="舊資料"),
        )
        assert old_outcome.stale is True
        latest_snapshot = await claim_suitability_job(
            session_factory,
            job_id=latest.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="latest-worker",
            worker_name="worker-b",
        )
        assert latest_snapshot is not None
        latest_outcome = await apply_suitability_result(
            session_factory,
            job_id=latest.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="latest-worker",
            snapshot=latest_snapshot,
            result=GeminiSuitabilityResult(score=91, explanation="最新資料"),
        )
        assert latest_outcome.applied is True
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                draft = await session.scalar(
                    select(AdoptionDraft).where(AdoptionDraft.id == draft_id)
                )
                assert draft is not None
                assert draft.interaction_version == 7
                assert draft.ai_suitability_score == 91
                assert draft.ai_suitability_explanation == "最新資料"
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_stale_running_job_recovers_once_then_uses_bounded_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    monkeypatch.setattr(get_worker_settings(), "celery_visibility_timeout", 1)
    monkeypatch.setattr(get_worker_settings(), "celery_max_retries", 1)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        first = await claim_suitability_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="worker-killed-before-commit",
            worker_name="worker-a",
        )
        assert first is not None
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                job = await session.scalar(
                    select(AIProcessingJob).where(AIProcessingJob.id == job_id).with_for_update()
                )
                assert job is not None
                job.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=2)

        recovered = await claim_suitability_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="replacement-worker",
            worker_name="worker-b",
        )

        assert recovered is not None
        assert recovered.skip_ai_reason == "lease_retry_exhausted"
        outcome = await apply_suitability_result(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="replacement-worker",
            snapshot=recovered,
            result=None,
            failure_reason=recovered.skip_ai_reason,
        )
        assert outcome.applied is True
        assert outcome.score is None
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_retry_budget_survives_fresh_reconciliation_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    monkeypatch.setattr(get_worker_settings(), "celery_max_retries", 2)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        for expected_retry_count in range(2):
            token = f"fresh-delivery-{expected_retry_count}"
            snapshot = await claim_suitability_job(
                session_factory,
                job_id=job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=4,
                claim_token=token,
                worker_name="replacement-worker",
            )
            assert snapshot is not None
            assert snapshot.retry_count == expected_retry_count
            await mark_suitability_retry(
                session_factory,
                job_id=job_id,
                organization_id=organization_id,
                claim_token=token,
                failure_reason="ReadTimeout",
                countdown=0,
            )

        exhausted = await claim_suitability_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="fresh-delivery-with-reset-celery-headers",
            worker_name="replacement-worker",
        )
        assert exhausted is not None
        assert exhausted.retry_count == 2
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_redelivery_after_domain_commit_sends_notification_without_rerunning_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    await _add_line_binding(adopter_id, f"U{adopter_id.hex}")
    pushed: list[str] = []
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        snapshot = await claim_suitability_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="worker-died-after-commit",
            worker_name="worker-a",
        )
        assert snapshot is not None
        outcome = await apply_suitability_result(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="worker-died-after-commit",
            snapshot=snapshot,
            result=GeminiSuitabilityResult(score=88, explanation="適合"),
        )
        assert outcome.applied is True

        def gemini_must_not_run(*_args, **_kwargs):
            raise AssertionError("Gemini must not run after the domain commit")

        async def record_push(*, job_id, **_kwargs) -> None:
            pushed.append(str(job_id))

        monkeypatch.setattr(adoption_task_module, "GeminiClient", gemini_must_not_run)
        monkeypatch.setattr(adoption_task_module, "_push_suitability_result", record_push)
        kwargs = {
            "job_id": str(job_id),
            "resource_id": str(draft_id),
            "organization_id": str(organization_id),
            "expected_version": 4,
        }

        first_delivery = await asyncio.to_thread(
            lambda: analyze_suitability.apply(kwargs=kwargs, task_id=str(job_id)).get()
        )
        duplicate_delivery = await asyncio.to_thread(
            lambda: analyze_suitability.apply(kwargs=kwargs, task_id=str(job_id)).get()
        )

        assert first_delivery == "succeeded"
        assert duplicate_delivery == "discarded_or_duplicate"
        assert pushed == [str(job_id)]
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                job = await session.scalar(
                    select(AIProcessingJob).where(AIProcessingJob.id == job_id)
                )
                assert job is not None
                assert job.validation_result["notification_status"] == "sent"
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_production_disabled_flag_skips_ai_without_background_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    token = str(draft_id)
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", False)
    try:
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                session.add(
                    AdoptionDraft(
                        id=draft_id,
                        opaque_token_digest=adoption_draft_token_digest(token),
                        organization_id=organization_id,
                        adopter_user_id=adopter_id,
                        path="specific_animal",
                        target_animal_id=animal_id,
                        current_step=AdoptionDraftState.CONFIRMING_ANSWERS.value,
                        answers={
                            "housing_type": "house",
                            "dog_experience": "first_time",
                            "other_pets": "none",
                            "household_members": "adults_only",
                            "work_schedule": "work_from_home",
                            "parenting_style": "structured",
                            "patience_level": "high_patience",
                            "adoption_motivation": "companionship",
                        },
                        reconfirmation_keys=[],
                        interaction_version=4,
                        status="active",
                        last_interaction_at=datetime.now(timezone.utc),
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    )
                )
                await session.flush()
                result = await LineAdoptionConversationService(
                    AdoptionDraftRepository(session, organization_id)
                ).handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_answers",
                    value=None,
                    event_id="production-safe-skip",
                )
                jobs = list(
                    (
                        await session.scalars(
                            select(AIProcessingJob).where(AIProcessingJob.target_id == draft_id)
                        )
                    ).all()
                )

        assert result.state == AdoptionDraftState.AWAITING_ADOPTER_NAME
        assert result.entered_awaiting_ai_suitability is False
        assert result.ai_job_id is None
        assert jobs == []
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_reconciliation_is_bounded_idempotent_and_excludes_legacy_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    published: list[dict] = []
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                job = await session.scalar(
                    select(AIProcessingJob).where(AIProcessingJob.id == job_id)
                )
                assert job is not None
                job.status = "pending_enqueue"

        monkeypatch.setattr(
            celery_app,
            "send_task",
            lambda *_args, **kwargs: published.append(kwargs) or SimpleNamespace(id=str(job_id)),
        )
        pending = await pending_celery_dispatches(
            session_factory,
            visibility_timeout=get_worker_settings().celery_visibility_timeout,
            limit=1000,
        )
        assert len(pending) <= 100
        assert (job_id, organization_id) in pending
        assert await _publish(session_factory, job_id=job_id, organization_id=organization_id)
        assert not await _publish(session_factory, job_id=job_id, organization_id=organization_id)
        assert len(published) == 1

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                job = await session.scalar(
                    select(AIProcessingJob).where(AIProcessingJob.id == job_id)
                )
                assert job is not None
                job.status = "pending_enqueue"
                job.execution_backend = "legacy_polling"
        pending = await pending_celery_dispatches(
            session_factory, visibility_timeout=get_worker_settings().celery_visibility_timeout
        )
        assert (job_id, organization_id) not in pending
        assert not await _publish(session_factory, job_id=job_id, organization_id=organization_id)
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_reconciliation_broker_failure_rolls_back_dispatch_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                job = await session.scalar(
                    select(AIProcessingJob).where(AIProcessingJob.id == job_id)
                )
                assert job is not None
                job.status = "pending_enqueue"

        def broker_down(*_args, **_kwargs):
            raise ConnectionError("redis unavailable")

        monkeypatch.setattr(celery_app, "send_task", broker_down)
        with pytest.raises(ConnectionError):
            await _publish(session_factory, job_id=job_id, organization_id=organization_id)
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                job = await session.scalar(
                    select(AIProcessingJob).where(AIProcessingJob.id == job_id)
                )
                assert job is not None
                assert job.status == "pending_enqueue"
                assert job.dispatched_at is None
    finally:
        await _cleanup(organization_id, adopter_id)


def test_celery_publish_fails_fast_for_reconciliation() -> None:
    transport_options = celery_app.conf.broker_transport_options

    assert transport_options["max_retries"] == 0
    assert transport_options["socket_connect_timeout"] == 1


@pytest.mark.asyncio
async def test_legacy_worker_cannot_claim_celery_suitability_job() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        async with session_factory() as session:
            async with session.begin():
                claimed = await WorkerJobRepository(
                    session, organization_id, worker_id="legacy-worker"
                ).claim_next()
                assert claimed is None
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_migration_refuses_unsafe_downgrade_with_durable_jobs() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        result = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "0052_adoption_growth_diary_features",
            ],
            env=dict(
                os.environ,
                DATABASE_URL=_database_url().replace("postgresql://", "postgresql+asyncpg://"),
            ),
            capture_output=True,
            timeout=30,
        )

        assert result.returncode != 0
        assert b"unsafe downgrade" in result.stderr
    finally:
        await _cleanup(organization_id, adopter_id)
        await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=dict(
                os.environ,
                DATABASE_URL=_database_url().replace("postgresql://", "postgresql+asyncpg://"),
            ),
            check=True,
            capture_output=True,
            timeout=30,
        )
