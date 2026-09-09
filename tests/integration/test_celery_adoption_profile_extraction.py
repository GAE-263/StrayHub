from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import services.worker.app.tasks.adoption as adoption_task_module
from fastapi import BackgroundTasks
from services.api.app.api.errors import DomainError
from services.api.app.api.line_webhook import _handle_adoption_text
from services.api.app.application.adoption_profile_extraction_job_service import (
    ProfileExtractionNotification,
    apply_profile_extraction_result,
    claim_profile_extraction_job,
    mark_profile_extraction_retry,
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
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
    adoption_draft_token_digest,
)
from services.worker.app.tasks.adoption import (
    _push_profile_extraction_result,
    extract_profile,
)
from services.worker.app.tasks.reconciliation import _publish
from sqlalchemy import select

from tests.integration.test_celery_adoption_suitability import (
    _add_line_binding,
    _base_rows,
    _cleanup,
)


async def _create_profile_draft(
    organization_id,
    adopter_id,
    animal_id,
    draft_id,
    *,
    answers: dict[str, str] | None = None,
    version: int = 3,
) -> None:
    async with session_factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        now = datetime.now(timezone.utc)
        session.add(
            AdoptionDraft(
                id=draft_id,
                opaque_token_digest=adoption_draft_token_digest(str(draft_id)),
                organization_id=organization_id,
                adopter_user_id=adopter_id,
                path="specific_animal",
                target_animal_id=animal_id,
                current_step=AdoptionDraftState.AWAITING_FREETEXT_PROFILE.value,
                answers=answers or {},
                reconfirmation_keys=[],
                freetext_profile_rounds=0,
                interaction_version=version,
                status="active",
                last_interaction_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )


async def _submit(organization_id, adopter_id, profile_text: str):
    async with session_factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        return await LineAdoptionConversationService(
            AdoptionDraftRepository(session, organization_id)
        ).submit_freetext_profile(
            adopter_user_id=adopter_id,
            profile_text=profile_text,
        )


@pytest.mark.asyncio
async def test_profile_command_persists_minimal_snapshot_and_primitive_payload(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    profile_text = "我住公寓，而且是第一次養狗"
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", True)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        result = await _submit(organization_id, adopter_id, profile_text)
        assert result.ai_job_id is not None
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(
                select(AIProcessingJob).where(AIProcessingJob.id == result.ai_job_id)
            )
            assert job is not None
            assert job.organization_id == organization_id
            assert job.domain_version == 4
            assert job.input_snapshot == {
                "profile_text": profile_text,
                "schema_version": "1",
                "source": "line_free_text",
            }
            payload = _payload(job)
        assert set(payload) == {
            "job_id",
            "resource_id",
            "organization_id",
            "expected_version",
        }
        assert profile_text not in str(payload)
        assert profile_text not in caplog.text
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_profile_command_rejects_oversized_text_without_job() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
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
async def test_profile_merge_fills_only_missing_answers() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_profile_draft(
            organization_id,
            adopter_id,
            animal_id,
            draft_id,
            answers={"housing_type": "house"},
        )
        command = await _submit(organization_id, adopter_id, "profile")
        assert command.ai_job_id is not None
        snapshot = await claim_profile_extraction_job(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="profile-worker",
            worker_name="worker-a",
        )
        assert snapshot is not None
        outcome = await apply_profile_extraction_result(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="profile-worker",
            extracted={
                "housing_type": "apartment_small",
                "dog_experience": "first_time",
                "other_pets": "none",
            },
        )
        assert outcome.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.scalar(select(AdoptionDraft).where(AdoptionDraft.id == draft_id))
            assert draft is not None
            assert draft.answers["housing_type"] == "house"
            assert draft.answers["dog_experience"] == "first_time"
            assert draft.answers["other_pets"] == "none"
            assert draft.interaction_version == 5
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_profile_write_time_validation_rejects_invalid_value_safely() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        command = await _submit(organization_id, adopter_id, "profile")
        assert command.ai_job_id is not None
        assert await claim_profile_extraction_job(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="write-validator",
            worker_name="worker-a",
        )
        outcome = await apply_profile_extraction_result(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="write-validator",
            extracted={"housing_type": "not-a-domain-option"},
        )
        assert outcome.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.scalar(select(AdoptionDraft).where(AdoptionDraft.id == draft_id))
            job = await session.scalar(
                select(AIProcessingJob).where(AIProcessingJob.id == command.ai_job_id)
            )
            assert draft is not None and "housing_type" not in draft.answers
            assert job is not None and job.raw_ai_output == {}
            assert job.validation_result["status"] == "fallback"
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_newer_profile_submission_discards_in_flight_older_job() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        first = await _submit(organization_id, adopter_id, "first profile")
        assert first.ai_job_id is not None
        first_snapshot = await claim_profile_extraction_job(
            session_factory,
            job_id=first.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="old-profile-worker",
            worker_name="worker-a",
        )
        assert first_snapshot is not None
        second = await _submit(organization_id, adopter_id, "new authoritative profile")
        assert second.ai_job_id is not None and second.ai_job_version == 5

        stale = await apply_profile_extraction_result(
            session_factory,
            job_id=first.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="old-profile-worker",
            extracted={"housing_type": "house"},
        )
        assert stale.stale is True
        latest_snapshot = await claim_profile_extraction_job(
            session_factory,
            job_id=second.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="new-profile-worker",
            worker_name="worker-b",
        )
        assert latest_snapshot is not None
        latest = await apply_profile_extraction_result(
            session_factory,
            job_id=second.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=5,
            claim_token="new-profile-worker",
            extracted={"housing_type": "apartment_large"},
        )
        assert latest.applied is True
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.scalar(select(AdoptionDraft).where(AdoptionDraft.id == draft_id))
            assert draft is not None
            assert draft.answers["housing_type"] == "apartment_large"
            assert draft.interaction_version == 6
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_profile_duplicate_claim_and_terminal_redelivery_are_idempotent() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        command = await _submit(organization_id, adopter_id, "profile")
        assert command.ai_job_id is not None

        async def claim(token: str):
            return await claim_profile_extraction_job(
                session_factory,
                job_id=command.ai_job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=4,
                claim_token=token,
                worker_name=token,
            )

        claims = await asyncio.gather(claim("worker-a"), claim("worker-b"))
        assert sum(item is not None for item in claims) == 1
        winner = "worker-a" if claims[0] is not None else "worker-b"
        outcome = await apply_profile_extraction_result(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token=winner,
            extracted={},
        )
        assert outcome.applied is True
        assert (
            await claim_profile_extraction_job(
                session_factory,
                job_id=command.ai_job_id,
                draft_id=draft_id,
                organization_id=organization_id,
                expected_version=4,
                claim_token="sequential-redelivery",
                worker_name="worker-c",
            )
            is None
        )
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_profile_tenant_forgery_and_retry_budget_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id, forged_organization_id = uuid4(), uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    monkeypatch.setattr(get_worker_settings(), "celery_max_retries", 1)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        command = await _submit(organization_id, adopter_id, "profile")
        assert command.ai_job_id is not None
        assert (
            await claim_profile_extraction_job(
                session_factory,
                job_id=command.ai_job_id,
                draft_id=draft_id,
                organization_id=forged_organization_id,
                expected_version=4,
                claim_token="forged",
                worker_name="attacker",
            )
            is None
        )
        snapshot = await claim_profile_extraction_job(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="retry-0",
            worker_name="worker-a",
        )
        assert snapshot is not None and snapshot.retry_count == 0
        await mark_profile_extraction_retry(
            session_factory,
            job_id=command.ai_job_id,
            organization_id=organization_id,
            claim_token="retry-0",
            failure_reason="ReadTimeout",
            countdown=0,
        )
        exhausted = await claim_profile_extraction_job(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="fresh-redelivery",
            worker_name="worker-b",
        )
        assert exhausted is not None and exhausted.retry_count == 1
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_profile_stale_running_claim_uses_bounded_safe_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    monkeypatch.setattr(get_worker_settings(), "celery_visibility_timeout", 1)
    monkeypatch.setattr(get_worker_settings(), "celery_max_retries", 1)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        command = await _submit(organization_id, adopter_id, "profile")
        assert command.ai_job_id is not None
        assert await claim_profile_extraction_job(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="worker-killed-after-gemini",
            worker_name="worker-a",
        )
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(
                select(AIProcessingJob)
                .where(AIProcessingJob.id == command.ai_job_id)
                .with_for_update()
            )
            assert job is not None
            job.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=2)
        recovered = await claim_profile_extraction_job(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="replacement-worker",
            worker_name="worker-b",
        )
        assert recovered is not None
        assert recovered.skip_ai_reason == "lease_retry_exhausted"
        outcome = await apply_profile_extraction_result(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="replacement-worker",
            extracted={},
            failure_reason=recovered.skip_ai_reason,
        )
        assert outcome.applied is True
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_production_disabled_profile_falls_back_to_explicit_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", False)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        tasks = BackgroundTasks()
        line = MockLineAdapter()
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            draft = await session.scalar(select(AdoptionDraft).where(AdoptionDraft.id == draft_id))
            assert draft is not None
            await _handle_adoption_text(
                session,
                line,
                {"webhookEventId": "safe-degraded", "source": {"userId": "U-safe"}},
                draft=draft,
                text="我住公寓",
                public_base_url=None,
                background_tasks=tasks,
            )
            jobs = list(
                (
                    await session.scalars(
                        select(AIProcessingJob).where(AIProcessingJob.target_id == draft_id)
                    )
                ).all()
            )
            assert draft.current_step != AdoptionDraftState.AWAITING_FREETEXT_PROFILE.value
        assert tasks.tasks == []
        assert jobs == []
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_recommend_path_profile_notification_does_not_run_legacy_curation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class FakeLine:
        async def push(self, **kwargs) -> None:
            calls.append({"profile_push": kwargs})

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(adoption_task_module.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(
        adoption_task_module,
        "LineMessagingApiAdapter",
        lambda **_kwargs: FakeLine(),
    )
    organization_id, job_id = uuid4(), uuid4()
    await _push_profile_extraction_result(
        organization_id=organization_id,
        job_id=job_id,
        notification=ProfileExtractionNotification(
            line_user_id="U-profile",
            path="recommend_me",
            answers={},
            state=AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS,
            actual_version=5,
        ),
    )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_profile_job_uses_existing_reconciliation_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    published: list[dict] = []
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        command = await _submit(organization_id, adopter_id, "profile")
        assert command.ai_job_id is not None
        monkeypatch.setattr(
            celery_app,
            "send_task",
            lambda *_args, **kwargs: (
                published.append(kwargs) or SimpleNamespace(id=str(command.ai_job_id))
            ),
        )
        assert await _publish(
            session_factory,
            job_id=command.ai_job_id,
            organization_id=organization_id,
        )
        assert len(published) == 1
        assert "profile" not in str(published[0])
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    ["pending_enqueue", "enqueue_failed", "retry_wait", "running"],
)
async def test_profile_reconciliation_discovers_each_recoverable_status(
    status: str,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        command = await _submit(organization_id, adopter_id, "profile")
        assert command.ai_job_id is not None
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(
                select(AIProcessingJob)
                .where(AIProcessingJob.id == command.ai_job_id)
                .with_for_update()
            )
            assert job is not None
            job.status = status
            job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            if status == "running":
                job.claimed_at = datetime.now(timezone.utc) - timedelta(days=1)
                job.claim_token = "dead-worker"
        pending = await pending_celery_dispatches(
            session_factory, visibility_timeout=get_worker_settings().celery_visibility_timeout
        )
        assert (command.ai_job_id, organization_id) in pending
    finally:
        await _cleanup(organization_id, adopter_id)


@pytest.mark.asyncio
async def test_profile_redelivery_after_commit_notifies_without_rerunning_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    await _add_line_binding(adopter_id, f"U{adopter_id.hex}")
    pushed: list[str] = []
    try:
        await _create_profile_draft(organization_id, adopter_id, animal_id, draft_id)
        command = await _submit(organization_id, adopter_id, "profile")
        assert command.ai_job_id is not None
        snapshot = await claim_profile_extraction_job(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="crash-after-commit",
            worker_name="worker-a",
        )
        assert snapshot is not None
        applied = await apply_profile_extraction_result(
            session_factory,
            job_id=command.ai_job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=4,
            claim_token="crash-after-commit",
            extracted={"housing_type": "house"},
        )
        assert applied.applied is True

        def gemini_must_not_run(*_args, **_kwargs):
            raise AssertionError("Gemini must not rerun after commit")

        async def record_push(*, job_id, **_kwargs) -> None:
            pushed.append(str(job_id))

        monkeypatch.setattr(adoption_task_module, "GeminiClient", gemini_must_not_run)
        monkeypatch.setattr(adoption_task_module, "_push_profile_extraction_result", record_push)
        kwargs = {
            "job_id": str(command.ai_job_id),
            "resource_id": str(draft_id),
            "organization_id": str(organization_id),
            "expected_version": 4,
        }
        first = await asyncio.to_thread(
            lambda: extract_profile.apply(kwargs=kwargs, task_id=str(command.ai_job_id)).get()
        )
        second = await asyncio.to_thread(
            lambda: extract_profile.apply(kwargs=kwargs, task_id=str(command.ai_job_id)).get()
        )
        assert first == "succeeded"
        assert second == "discarded_or_duplicate"
        assert pushed == [str(command.ai_job_id)]
    finally:
        await _cleanup(organization_id, adopter_id)
