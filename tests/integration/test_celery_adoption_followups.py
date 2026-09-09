from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import services.worker.app.tasks.adoption as adoption_task_module
from fastapi import BackgroundTasks
from services.api.app.api.errors import DomainError
from services.api.app.api.line_webhook import _handle_adoption_text
from services.api.app.application.adoption_followup_job_service import (
    apply_followup_result,
    claim_followup_job,
    mark_followup_retry,
)
from services.api.app.application.celery_job_dispatch import (
    _payload,
    pending_celery_dispatches,
)
from services.api.app.application.line_adoption_conversation import (
    LineAdoptionConversationService,
)
from services.api.app.config.settings import get_settings, get_worker_settings
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.infrastructure.ai.gemini_client import GeminiAnimalRecommendation
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
    adoption_draft_token_digest,
)
from services.worker.app.tasks.adoption import generate_followups
from sqlalchemy import select

from tests.integration.test_celery_adoption_suitability import (
    _add_line_binding,
    _base_rows,
    _cleanup,
)


async def _create_followup_draft(organization_id, adopter_id, target_id, draft_id) -> None:
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
                target_animal_id=target_id,
                current_step=AdoptionDraftState.AWAITING_AI_SUITABILITY.value,
                answers={},
                reconfirmation_keys=[],
                candidate_match_ids=[],
                match_results=[],
                ai_followup_target_animal_id=target_id,
                interaction_version=5,
                status="active",
                last_interaction_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )


async def _add_candidates(organization_id, count: int) -> list:
    ids = [uuid4() for _ in range(count)]
    async with session_factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        session.add_all(
            [
                Animal(
                    id=animal_id,
                    organization_id=organization_id,
                    name=f"候選{i:03d}",
                    shelter_number=f"C{i:03d}-{animal_id.hex[:8]}",
                    status="active",
                    is_adoptable=True,
                    size="medium",
                    energy="medium",
                    temperament=[],
                )
                for i, animal_id in enumerate(ids)
            ]
        )
    return ids


async def _submit(organization_id, adopter_id, text: str):
    async with session_factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        return await LineAdoptionConversationService(
            AdoptionDraftRepository(session, organization_id)
        ).submit_followup_request(adopter_user_id=adopter_id, special_request=text)


@pytest.mark.asyncio
async def test_followup_snapshot_freezes_request_and_bounded_candidate_ids() -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    request = "希望個性安靜、能和小朋友相處"
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    await _add_candidates(organization_id, 500)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, request)
        assert result.ai_job_id is not None and result.ai_job_version == 6
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(
                select(AIProcessingJob).where(AIProcessingJob.id == result.ai_job_id)
            )
            assert job is not None
            snapshot = job.input_snapshot
            assert snapshot["special_request"] == request
            assert snapshot["target_animal_id"] == str(target_id)
            assert len(snapshot["candidate_ids"]) == 30
            assert str(target_id) not in snapshot["candidate_ids"]
            payload = _payload(job)
        assert request not in str(payload)
        assert set(payload) == {
            "job_id",
            "resource_id",
            "organization_id",
            "expected_version",
        }
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_followup_command_rejects_oversized_request_without_job() -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        with pytest.raises(DomainError) as caught:
            await _submit(organization_id, adopter_id, "x" * 2001)
        assert caught.value.status_code == 422
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            assert (
                await session.scalar(
                    select(AIProcessingJob.id).where(AIProcessingJob.target_id == draft_id)
                )
                is None
            )
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_followup_claim_drops_candidates_that_are_no_longer_authorized() -> None:
    organization_id, other_org = uuid4(), uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    other_user, other_animal = uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    await _base_rows(other_org, other_user, other_animal)
    candidates = await _add_candidates(organization_id, 3)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            animals = list(
                (await session.scalars(select(Animal).where(Animal.id.in_(candidates[:2])))).all()
            )
            animals[0].status = "adopted"
            animals[1].is_adoptable = False
            job = await session.scalar(
                select(AIProcessingJob).where(AIProcessingJob.id == result.ai_job_id)
            )
            assert job is not None
            snapshot = dict(job.input_snapshot)
            snapshot["candidate_ids"] = [*snapshot["candidate_ids"], str(other_animal)]
            job.input_snapshot = snapshot
        claimed = await claim_followup_job(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="candidate-filter",
            worker_name="worker-a",
        )
        assert claimed is not None
        assert claimed.candidate_ids == (candidates[2],)
        assert str(other_animal) not in claimed.prompt
    finally:
        await _cleanup(organization_id, adopter_id)
        await _cleanup(other_org, other_user)


@pytest.mark.asyncio
async def test_followup_forged_organization_cannot_claim_job() -> None:
    organization_id, forged_org = uuid4(), uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    await _add_candidates(organization_id, 1)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None
        assert (
            await claim_followup_job(
                session_factory,
                job_id=result.ai_job_id,
                draft_id=draft_id,
                organization_id=forged_org,
                expected_version=6,
                claim_token="forged",
                worker_name="attacker",
            )
            is None
        )
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_followup_write_rejects_non_snapshot_id_and_preserves_original() -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    await _add_candidates(organization_id, 2)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None
        assert await claim_followup_job(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="strict-write",
            worker_name="worker-a",
        )
        outcome = await apply_followup_result(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="strict-write",
            recommendations=[GeminiAnimalRecommendation(animal_id=str(uuid4()), reason="偽造")],
        )
        assert outcome.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            assert draft.candidate_match_ids == [str(target_id)]
            assert draft.current_step == AdoptionDraftState.SELECTING_ALTERNATIVE_ANIMAL.value
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_followup_drops_recommendation_that_became_unavailable_during_ai() -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    candidate_id = (await _add_candidates(organization_id, 1))[0]
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None
        claimed = await claim_followup_job(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="in-flight",
            worker_name="worker-a",
        )
        assert claimed is not None and candidate_id in claimed.candidate_ids
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            candidate = await session.get(Animal, candidate_id)
            assert candidate is not None
            candidate.status = "adopted"
        outcome = await apply_followup_result(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="in-flight",
            recommendations=[
                GeminiAnimalRecommendation(animal_id=str(candidate_id), reason="很安靜")
            ],
        )
        assert outcome.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None and draft.candidate_match_ids == [str(target_id)]
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_followup_with_no_available_animals_safely_advances_to_contact() -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None
        claimed = await claim_followup_job(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="empty-fallback",
            worker_name="worker-a",
        )
        assert claimed is not None and claimed.skip_ai_reason == "no_valid_candidates"
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            target = await session.get(Animal, target_id)
            assert target is not None
            target.status = "adopted"
        outcome = await apply_followup_result(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="empty-fallback",
            recommendations=[],
            failure_reason=claimed.skip_ai_reason,
        )
        assert outcome.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            assert draft.current_step == AdoptionDraftState.AWAITING_ADOPTER_NAME.value
            assert draft.candidate_match_ids == []
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_newer_special_request_discards_older_in_flight_job() -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    candidate_id = (await _add_candidates(organization_id, 1))[0]
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        first = await _submit(organization_id, adopter_id, "需求 A")
        assert first.ai_job_id is not None
        assert await claim_followup_job(
            session_factory,
            job_id=first.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="old-worker",
            worker_name="worker-a",
        )
        second = await _submit(organization_id, adopter_id, "需求 B")
        assert second.ai_job_id is not None and second.ai_job_version == 7
        stale = await apply_followup_result(
            session_factory,
            job_id=first.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="old-worker",
            recommendations=[
                GeminiAnimalRecommendation(animal_id=str(candidate_id), reason="舊結果")
            ],
        )
        assert stale.stale is True
        latest = await claim_followup_job(
            session_factory,
            job_id=second.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=7,
            claim_token="new-worker",
            worker_name="worker-b",
        )
        assert latest is not None and "需求 B" in latest.prompt
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_followup_cancel_during_ai_discards_without_domain_effect() -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    candidate_id = (await _add_candidates(organization_id, 1))[0]
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None
        assert await claim_followup_job(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="cancelled-worker",
            worker_name="worker-a",
        )
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            draft.status = "cancelled"
            draft.current_step = AdoptionDraftState.CANCELLED.value
            draft.interaction_version += 1
        outcome = await apply_followup_result(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="cancelled-worker",
            recommendations=[
                GeminiAnimalRecommendation(animal_id=str(candidate_id), reason="舊結果")
            ],
        )
        assert outcome.stale is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None and draft.candidate_match_ids == []
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_followup_duplicate_claim_retry_budget_and_stale_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    await _add_candidates(organization_id, 1)
    monkeypatch.setattr(get_worker_settings(), "celery_visibility_timeout", 1)
    monkeypatch.setattr(get_worker_settings(), "celery_max_retries", 1)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None

        async def claim(token: str):
            return await claim_followup_job(
                session_factory,
                job_id=result.ai_job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=6,
                claim_token=token,
                worker_name=token,
            )

        claims = await asyncio.gather(claim("worker-a"), claim("worker-b"))
        assert sum(item is not None for item in claims) == 1
        winner = "worker-a" if claims[0] is not None else "worker-b"
        await mark_followup_retry(
            session_factory,
            job_id=result.ai_job_id,
            organization_id=organization_id,
            claim_token=winner,
            failure_reason="ReadTimeout",
            countdown=0,
        )
        newly_added = (await _add_candidates(organization_id, 1))[0]
        reclaimed = await claim("worker-c")
        assert reclaimed is not None and reclaimed.retry_count == 1
        assert newly_added not in reclaimed.candidate_ids
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, result.ai_job_id)
            assert job is not None
            job.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=2)
        recovered_after_crash = await claim("worker-d")
        assert recovered_after_crash is not None
        assert recovered_after_crash.skip_ai_reason == "lease_retry_exhausted"
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending_enqueue", "enqueue_failed", "retry_wait", "running"])
async def test_followup_reconciliation_discovers_recoverable_status(status: str) -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    await _add_candidates(organization_id, 1)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, result.ai_job_id)
            assert job is not None
            job.status = status
            job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            if status == "running":
                job.claimed_at = datetime.now(timezone.utc) - timedelta(days=1)
                job.claim_token = "dead-worker"
        assert (result.ai_job_id, organization_id) in await pending_celery_dispatches(
            session_factory
        )
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_followup_redelivery_after_commit_does_not_rerun_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    await _add_line_binding(adopter_id, f"U{adopter_id.hex}")
    await _add_candidates(organization_id, 1)
    pushed: list[str] = []
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        result = await _submit(organization_id, adopter_id, "安靜")
        assert result.ai_job_id is not None
        snapshot = await claim_followup_job(
            session_factory,
            job_id=result.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=6,
            claim_token="commit-worker",
            worker_name="worker-a",
        )
        assert snapshot is not None
        assert (
            await apply_followup_result(
                session_factory,
                job_id=result.ai_job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=6,
                claim_token="commit-worker",
                recommendations=[],
            )
        ).applied

        def gemini_must_not_run(*_args, **_kwargs):
            raise AssertionError("Gemini must not rerun after domain commit")

        async def record_push(*, job_id, **_kwargs) -> None:
            pushed.append(str(job_id))

        monkeypatch.setattr(adoption_task_module, "GeminiClient", gemini_must_not_run)
        monkeypatch.setattr(adoption_task_module, "_push_followup_result", record_push)
        kwargs = {
            "job_id": str(result.ai_job_id),
            "resource_id": str(draft_id),
            "organization_id": str(organization_id),
            "expected_version": 6,
        }
        assert (
            await asyncio.to_thread(
                lambda: generate_followups.apply(kwargs=kwargs, task_id=str(result.ai_job_id)).get()
            )
            == "succeeded"
        )
        assert (
            await asyncio.to_thread(
                lambda: generate_followups.apply(kwargs=kwargs, task_id=str(result.ai_job_id)).get()
            )
            == "discarded_or_duplicate"
        )
        assert pushed == [str(result.ai_job_id)]
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_production_disabled_followup_has_no_ai_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, target_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, target_id)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", False)
    try:
        await _create_followup_draft(organization_id, adopter_id, target_id, draft_id)
        tasks, line = BackgroundTasks(), MockLineAdapter()
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            await _handle_adoption_text(
                session,
                line,
                {"webhookEventId": "degraded", "source": {"userId": "U-safe"}},
                draft=draft,
                text="安靜",
                public_base_url=None,
                background_tasks=tasks,
            )
            assert draft.current_step == AdoptionDraftState.SELECTING_ALTERNATIVE_ANIMAL.value
            assert (
                await session.scalar(
                    select(AIProcessingJob.id).where(AIProcessingJob.target_id == draft_id)
                )
                is None
            )
        assert tasks.tasks == []
    finally:
        await _cleanup(organization_id, adopter_id)
