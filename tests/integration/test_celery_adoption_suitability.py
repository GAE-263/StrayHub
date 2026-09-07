from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.application.adoption_suitability_job_service import (
    apply_suitability_result,
    claim_suitability_job,
)
from services.api.app.application.celery_job_dispatch import dispatch_ai_job
from services.api.app.application.line_adoption_conversation import (
    LineAdoptionConversationService,
)
from services.api.app.config.settings import get_settings
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
        assert await dispatch_ai_job(result.ai_job_id, organization_id) is False
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
        assert await dispatch_ai_job(result.ai_job_id, organization_id) is True

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
