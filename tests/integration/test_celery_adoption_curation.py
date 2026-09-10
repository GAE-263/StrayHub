from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import services.worker.app.tasks.adoption as adoption_task_module
from fastapi import BackgroundTasks
from services.api.app.api.line_webhook import _handle_adoption_postback
from services.api.app.application.adoption_curation_job_service import (
    apply_curation_result,
    claim_curation_job,
    mark_curation_retry,
)
from services.api.app.application.adoption_profile_extraction_job_service import (
    apply_profile_extraction_result,
    claim_profile_extraction_job,
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
from services.api.app.infrastructure.ai.gemini_client import GeminiRankedRecommendation
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
from services.worker.app.tasks.adoption import curate_recommendations
from sqlalchemy import select

from tests.integration.test_celery_adoption_followups import _add_candidates
from tests.integration.test_celery_adoption_suitability import (
    _add_line_binding,
    _base_rows,
    _cleanup,
)

PREFERENCES = {
    "housing_type": "house",
    "dog_experience": "experienced",
    "other_pets": "none",
    "household_members": "adults_only",
    "work_schedule": "work_from_home",
    "parenting_style": "structured",
    "patience_level": "high_patience",
    "adoption_motivation": "companionship",
    "preferred_size": "medium",
}


async def _create_draft(organization_id, adopter_id, draft_id, *, version: int = 4) -> None:
    now = datetime.now(timezone.utc)
    async with session_factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        session.add(
            AdoptionDraft(
                id=draft_id,
                opaque_token_digest=adoption_draft_token_digest(str(draft_id)),
                organization_id=organization_id,
                adopter_user_id=adopter_id,
                path="recommend_me",
                target_animal_id=None,
                current_step=AdoptionDraftState.ANSWERING_PREFERENCE_ENERGY.value,
                answers=dict(PREFERENCES),
                reconfirmation_keys=[],
                candidate_match_ids=[],
                match_results=[],
                interaction_version=version,
                status="active",
                last_interaction_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )


async def _start_curation(organization_id, adopter_id, draft_id):
    async with session_factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        return await LineAdoptionConversationService(
            AdoptionDraftRepository(session, organization_id)
        ).handle(
            token=str(draft_id),
            adopter_user_id=adopter_id,
            action="answer",
            value="medium",
            event_id=uuid4().hex,
        )


@pytest.mark.asyncio
async def test_curation_command_freezes_rule_order_metadata_and_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, first_animal, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, first_animal)
    await _add_candidates(organization_id, 500)
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", True)
    try:
        await _create_draft(organization_id, adopter_id, draft_id)
        result = await _start_curation(organization_id, adopter_id, draft_id)
        assert result.ai_job_id is not None and result.ai_job_version == 5
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, result.ai_job_id)
            assert job is not None
            snapshot = job.input_snapshot
            assert 1 <= len(snapshot["candidate_ids"]) <= 5
            assert snapshot["candidate_ids"] == [
                item["animal_id"] for item in snapshot["rule_results"]
            ]
            assert snapshot["preferences"] == {**PREFERENCES, "preferred_energy": "medium"}
            assert snapshot["source"] == "rule_based_matching"
            payload = _payload(job)
        assert set(payload) == {
            "job_id",
            "resource_id",
            "organization_id",
            "expected_version",
        }
        assert "housing_type" not in str(payload)
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_profile_completion_creates_durable_curation_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, first_animal, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, first_animal)
    await _add_candidates(organization_id, 3)
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", True)
    try:
        now = datetime.now(timezone.utc)
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            session.add(
                AdoptionDraft(
                    id=draft_id,
                    opaque_token_digest=adoption_draft_token_digest(str(draft_id)),
                    organization_id=organization_id,
                    adopter_user_id=adopter_id,
                    path="recommend_me",
                    current_step=AdoptionDraftState.AWAITING_FREETEXT_PROFILE.value,
                    answers={**PREFERENCES, "preferred_energy": "medium"},
                    reconfirmation_keys=[],
                    freetext_profile_rounds=1,
                    candidate_match_ids=[],
                    match_results=[],
                    interaction_version=3,
                    status="active",
                    last_interaction_at=now,
                    expires_at=now + timedelta(hours=1),
                )
            )
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            profile_command = await LineAdoptionConversationService(
                AdoptionDraftRepository(session, organization_id)
            ).submit_freetext_profile(
                adopter_user_id=adopter_id,
                profile_text="生活條件已完整",
            )
        assert profile_command.ai_job_id is not None
        assert await claim_profile_extraction_job(
            session_factory,
            job_id=profile_command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="profile-to-curation",
            worker_name="worker-a",
        )
        outcome = await apply_profile_extraction_result(
            session_factory,
            job_id=profile_command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="profile-to-curation",
            extracted={},
        )
        assert outcome.applied is True and outcome.next_job_id is not None
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            curation_job = await session.get(AIProcessingJob, outcome.next_job_id)
            assert curation_job is not None
            assert curation_job.job_type == "adoption_recommendation_curation"
            assert curation_job.domain_version == 5
    finally:
        await _cleanup(organization_id, adopter_id)


async def _setup_job(monkeypatch: pytest.MonkeyPatch, *, candidate_count: int = 3):
    organization_id = uuid4()
    adopter_id, first_animal, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, first_animal)
    await _add_candidates(organization_id, candidate_count)
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", True)
    await _create_draft(organization_id, adopter_id, draft_id)
    result = await _start_curation(organization_id, adopter_id, draft_id)
    assert result.ai_job_id is not None
    return organization_id, adopter_id, draft_id, result.ai_job_id


@pytest.mark.asyncio
async def test_curation_preserves_gemini_order_and_selected_subset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, adopter_id, draft_id, job_id = await _setup_job(monkeypatch)
    try:
        snapshot = await claim_curation_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="ordering",
            worker_name="worker-a",
        )
        assert snapshot is not None and len(snapshot.candidate_ids) >= 3
        third, first = snapshot.candidate_ids[2], snapshot.candidate_ids[0]
        outcome = await apply_curation_result(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="ordering",
            recommendations=[
                GeminiRankedRecommendation(str(third), 95, "最適合"),
                GeminiRankedRecommendation(str(first), 88, "第二名"),
            ],
        )
        assert outcome.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            assert draft.candidate_match_ids == [str(third), str(first)]
            assert [item["score"] for item in draft.match_results] == [95, 88]
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_curation_invalid_id_and_empty_output_fall_back_to_rule_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, adopter_id, draft_id, job_id = await _setup_job(monkeypatch)
    try:
        snapshot = await claim_curation_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="fallback",
            worker_name="worker-a",
        )
        assert snapshot is not None
        outcome = await apply_curation_result(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="fallback",
            recommendations=[GeminiRankedRecommendation(str(uuid4()), 99, "invented")],
        )
        assert outcome.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            assert draft.candidate_match_ids == [str(item) for item in snapshot.candidate_ids]
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("new_status", ["adopted", "inactive", "removed"])
async def test_curation_drops_candidate_invalidated_during_gemini(
    monkeypatch: pytest.MonkeyPatch, new_status: str
) -> None:
    organization_id, adopter_id, draft_id, job_id = await _setup_job(monkeypatch)
    try:
        snapshot = await claim_curation_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="invalidation",
            worker_name="worker-a",
        )
        assert snapshot is not None and len(snapshot.candidate_ids) >= 2
        invalid, valid = snapshot.candidate_ids[:2]
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            animal = await session.get(Animal, invalid)
            assert animal is not None
            if new_status == "removed":
                await session.delete(animal)
            else:
                animal.status = new_status
        outcome = await apply_curation_result(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="invalidation",
            recommendations=[
                GeminiRankedRecommendation(str(invalid), 99, "失效"),
                GeminiRankedRecommendation(str(valid), 90, "有效"),
            ],
        )
        assert outcome.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            assert str(invalid) not in draft.candidate_match_ids
            assert draft.candidate_match_ids == [str(valid)]
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("user_action", ["cancel", "back", "new_cycle"])
async def test_curation_stale_user_action_has_zero_domain_effect(
    monkeypatch: pytest.MonkeyPatch, user_action: str
) -> None:
    organization_id, adopter_id, draft_id, job_id = await _setup_job(monkeypatch)
    try:
        snapshot = await claim_curation_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="stale",
            worker_name="worker-a",
        )
        assert snapshot is not None
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            original_ids = list(draft.candidate_match_ids)
            if user_action == "cancel":
                draft.status = "cancelled"
                draft.current_step = AdoptionDraftState.CANCELLED.value
            elif user_action == "back":
                draft.current_step = AdoptionDraftState.PRESENTING_MATCHES.value
            else:
                original_ids = list(reversed(original_ids))
                draft.candidate_match_ids = original_ids
            draft.interaction_version += 1
        outcome = await apply_curation_result(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="stale",
            recommendations=[
                GeminiRankedRecommendation(str(snapshot.candidate_ids[0]), 90, "舊結果")
            ],
        )
        assert outcome.stale is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None and draft.candidate_match_ids == original_ids
            job = await session.get(AIProcessingJob, job_id)
            assert job is not None and job.status == "discarded"
            assert "notification_status" not in (job.validation_result or {})
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_curation_duplicate_claim_retry_and_stale_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, adopter_id, draft_id, job_id = await _setup_job(monkeypatch)
    monkeypatch.setattr(get_worker_settings(), "celery_visibility_timeout", 1)
    monkeypatch.setattr(get_worker_settings(), "celery_max_retries", 1)
    try:

        async def claim(token: str):
            return await claim_curation_job(
                session_factory,
                job_id=job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=5,
                claim_token=token,
                worker_name=token,
            )

        claims = await asyncio.gather(claim("worker-a"), claim("worker-b"))
        assert sum(item is not None for item in claims) == 1
        winner = "worker-a" if claims[0] is not None else "worker-b"
        first_snapshot = claims[0] if claims[0] is not None else claims[1]
        assert first_snapshot is not None
        await mark_curation_retry(
            session_factory,
            job_id=job_id,
            organization_id=organization_id,
            claim_token=winner,
            failure_reason="ReadTimeout",
            countdown=0,
        )
        retried = await claim("worker-c")
        assert retried is not None and retried.retry_count == 1
        assert retried.candidate_ids == first_snapshot.candidate_ids
        assert retried.prompt == first_snapshot.prompt
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, job_id)
            assert job is not None
            job.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=2)
        recovered = await claim("worker-d")
        assert recovered is not None and recovered.skip_ai_reason == "lease_retry_exhausted"
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending_enqueue", "enqueue_failed", "retry_wait", "running"])
async def test_curation_reconciliation_discovers_recoverable_status(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    organization_id, adopter_id, _draft_id, job_id = await _setup_job(monkeypatch)
    try:
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, job_id)
            assert job is not None
            job.status = status
            job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            if status == "running":
                job.claimed_at = datetime.now(timezone.utc) - timedelta(days=1)
                job.claim_token = "dead-worker"
        assert (job_id, organization_id) in await pending_celery_dispatches(
            session_factory, visibility_timeout=get_worker_settings().celery_visibility_timeout
        )
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_curation_forged_tenant_cannot_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, adopter_id, draft_id, job_id = await _setup_job(monkeypatch)
    try:
        assert (
            await claim_curation_job(
                session_factory,
                job_id=job_id,
                draft_id=draft_id,
                organization_id=uuid4(),
                expected_version=5,
                claim_token="forged",
                worker_name="attacker",
            )
            is None
        )
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_curation_snapshot_cannot_expand_rule_engine_universe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, adopter_id, draft_id, job_id = await _setup_job(monkeypatch)
    other_org, other_user, other_animal = uuid4(), uuid4(), uuid4()
    await _base_rows(other_org, other_user, other_animal)
    try:
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, job_id)
            assert job is not None
            snapshot = dict(job.input_snapshot)
            candidate_ids = list(snapshot["candidate_ids"])
            rule_results = list(snapshot["rule_results"])
            candidate_ids[0] = str(other_animal)
            rule_results[0] = {
                "animal_id": str(other_animal),
                "score": 100,
                "reasons": ["forged"],
            }
            snapshot["candidate_ids"] = candidate_ids
            snapshot["rule_results"] = rule_results
            job.input_snapshot = snapshot
        assert (
            await claim_curation_job(
                session_factory,
                job_id=job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=5,
                claim_token="tampered-snapshot",
                worker_name="worker-a",
            )
            is None
        )
    finally:
        await _cleanup(organization_id, adopter_id)
        await _cleanup(other_org, other_user)


@pytest.mark.asyncio
async def test_curation_redelivery_after_commit_does_not_rerun_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, adopter_id, draft_id, job_id = await _setup_job(monkeypatch)
    await _add_line_binding(adopter_id, f"U{adopter_id.hex}")
    pushed: list[str] = []
    try:
        snapshot = await claim_curation_job(
            session_factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="commit",
            worker_name="worker-a",
        )
        assert snapshot is not None
        assert (
            await apply_curation_result(
                session_factory,
                job_id=job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=5,
                claim_token="commit",
                recommendations=[],
            )
        ).applied

        def gemini_must_not_run(*_args, **_kwargs):
            raise AssertionError("Gemini must not rerun")

        async def record_push(*, job_id, **_kwargs) -> None:
            pushed.append(str(job_id))

        monkeypatch.setattr(adoption_task_module, "GeminiClient", gemini_must_not_run)
        monkeypatch.setattr(adoption_task_module, "_push_curation_result", record_push)
        kwargs = {
            "job_id": str(job_id),
            "resource_id": str(draft_id),
            "organization_id": str(organization_id),
            "expected_version": 5,
        }
        assert (
            await asyncio.to_thread(
                lambda: curate_recommendations.apply(kwargs=kwargs, task_id=str(job_id)).get()
            )
            == "succeeded"
        )
        assert (
            await asyncio.to_thread(
                lambda: curate_recommendations.apply(kwargs=kwargs, task_id=str(job_id)).get()
            )
            == "discarded_or_duplicate"
        )
        assert pushed == [str(job_id)]
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_production_disabled_curation_uses_rule_results_without_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, first_animal, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, first_animal)
    await _add_candidates(organization_id, 3)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", False)
    try:
        await _create_draft(organization_id, adopter_id, draft_id)
        result = await _start_curation(organization_id, adopter_id, draft_id)
        assert result.ai_job_id is None
        assert result.state == AdoptionDraftState.SELECTING_MATCHED_ANIMAL
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            jobs = list(
                (
                    await session.scalars(
                        select(AIProcessingJob).where(AIProcessingJob.target_id == draft_id)
                    )
                ).all()
            )
            assert draft is not None and draft.candidate_match_ids
            assert jobs == []
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_production_disabled_curation_registers_no_gemini_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, first_animal, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, first_animal)
    await _add_candidates(organization_id, 5)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", False)
    tasks, line = BackgroundTasks(), MockLineAdapter()
    try:
        await _create_draft(organization_id, adopter_id, draft_id)
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.get(AdoptionDraft, draft_id)
            assert draft is not None
            await _handle_adoption_postback(
                session,
                line,
                {
                    "webhookEventId": "curation-degraded",
                    "replyToken": "reply-token",
                    "source": {"userId": "U-safe"},
                    "postback": {
                        "data": (
                            "action=answer&value=medium&question=preferred_energy"
                            "&step=answering_preference_energy&version=4"
                        )
                    },
                },
                draft=draft,
                public_base_url=None,
                background_tasks=tasks,
            )
            assert draft.current_step == AdoptionDraftState.SELECTING_MATCHED_ANIMAL.value
        assert tasks.tasks == []
    finally:
        await _cleanup(organization_id, adopter_id)
