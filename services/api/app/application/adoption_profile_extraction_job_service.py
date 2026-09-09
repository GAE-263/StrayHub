from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.app.application.adoption_ai_analysis_service import (
    build_profile_extraction_prompt,
    profile_extraction_contract,
)
from services.api.app.application.line_adoption_conversation import (
    LineAdoptionConversationService,
)
from services.api.app.config.settings import get_worker_settings
from services.api.app.domain.line_adoption_state import AdoptionDraftState, AdoptionPath
from services.api.app.infrastructure.ai.gemini_client import MalformedAiResponse
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.identity import LineUserBinding
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
)

JOB_TYPE = "adoption_profile_extraction"
TARGET_TYPE = "adoption_draft"
CLAIMABLE = {"pending_enqueue", "enqueue_failed", "queued", "retry_wait"}
TERMINAL = {"succeeded", "failed", "discarded"}
NOTIFICATION_CLAIMABLE = {"pending", "retry_wait", "failed"}


@dataclass(frozen=True)
class ProfileExtractionSnapshot:
    prompt: str
    valid_values: dict[str, set[str]]
    retry_count: int
    skip_ai_reason: str | None = None


@dataclass(frozen=True)
class ProfileExtractionOutcome:
    applied: bool
    stale: bool = False
    actual_version: int | None = None
    next_job_id: UUID | None = None


@dataclass(frozen=True)
class ProfileExtractionNotification:
    line_user_id: str
    path: str
    answers: dict[str, str]
    state: AdoptionDraftState
    actual_version: int


async def claim_profile_extraction_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    worker_name: str,
) -> ProfileExtractionSnapshot | None:
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
                AIProcessingJob.target_type == TARGET_TYPE,
                AIProcessingJob.target_id == draft_id,
                AIProcessingJob.domain_version == expected_version,
                AIProcessingJob.execution_backend == "celery",
            )
            .with_for_update()
        )
        if job is None or job.status in TERMINAL:
            return None
        now = datetime.now(timezone.utc)
        if job.status == "retry_wait" and job.available_at is not None:
            available_at = _aware(job.available_at)
            if available_at > now:
                return None
        skip_ai_reason: str | None = None
        if job.status == "running":
            stale_before = now - timedelta(seconds=get_worker_settings().celery_visibility_timeout)
            claimed_at = _aware(job.claimed_at) if job.claimed_at is not None else None
            if claimed_at is not None and claimed_at >= stale_before:
                return None
            job.retry_count = (job.retry_count or 0) + 1
            if job.retry_count >= get_worker_settings().celery_max_retries:
                skip_ai_reason = "lease_retry_exhausted"
        if job.status not in CLAIMABLE and job.status != "running":
            return None
        draft = await session.scalar(
            select(AdoptionDraft)
            .where(
                AdoptionDraft.id == draft_id,
                AdoptionDraft.organization_id == organization_id,
            )
            .with_for_update()
        )
        if (
            draft is None
            or draft.status != "active"
            or draft.current_step != AdoptionDraftState.AWAITING_FREETEXT_PROFILE.value
            or draft.interaction_version != expected_version
            or draft.path not in {path.value for path in AdoptionPath}
        ):
            _discard(job, "stale_domain_state")
            return None
        snapshot = job.input_snapshot
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "profile_text",
            "schema_version",
            "source",
        }:
            _discard(job, "invalid_input_snapshot")
            return None
        profile_text = snapshot.get("profile_text")
        if (
            not isinstance(profile_text, str)
            or not profile_text.strip()
            or len(profile_text) > 2000
            or snapshot.get("schema_version") != "1"
            or snapshot.get("source") != "line_free_text"
        ):
            _discard(job, "invalid_input_snapshot")
            return None
        include_recommend_me_keys = draft.path == AdoptionPath.RECOMMEND_ME.value
        prompt, valid_values = build_profile_extraction_prompt(
            profile_text,
            include_recommend_me_keys=include_recommend_me_keys,
        )
        job.status = "running"
        job.claim_token = claim_token
        job.claimed_by = worker_name[:120]
        job.claimed_at = now
        job.started_at = job.started_at or now
        job.available_at = None
        return ProfileExtractionSnapshot(
            prompt=prompt,
            valid_values=valid_values,
            retry_count=job.retry_count or 0,
            skip_ai_reason=skip_ai_reason,
        )


async def apply_profile_extraction_result(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    extracted: dict[str, str],
    failure_reason: str | None = None,
) -> ProfileExtractionOutcome:
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
                AIProcessingJob.target_id == draft_id,
                AIProcessingJob.domain_version == expected_version,
            )
            .with_for_update()
        )
        draft = await session.scalar(
            select(AdoptionDraft)
            .where(
                AdoptionDraft.id == draft_id,
                AdoptionDraft.organization_id == organization_id,
            )
            .with_for_update()
        )
        if job is None or job.status != "running" or job.claim_token != claim_token:
            return ProfileExtractionOutcome(applied=False)
        if (
            draft is None
            or draft.status != "active"
            or draft.current_step != AdoptionDraftState.AWAITING_FREETEXT_PROFILE.value
            or draft.interaction_version != expected_version
            or draft.path not in {path.value for path in AdoptionPath}
        ):
            _discard(job, "stale_domain_state")
            return ProfileExtractionOutcome(
                applied=False,
                stale=True,
                actual_version=draft.interaction_version if draft is not None else None,
            )
        try:
            _validate_extracted(extracted, path=AdoptionPath(draft.path))
        except MalformedAiResponse as exc:
            # Treat a value that fails the write-time defense as an empty,
            # non-authoritative extraction. The workflow can continue with
            # explicit questions and the invalid value never reaches answers.
            extracted = {}
            failure_reason = failure_reason or f"malformed:{type(exc).__name__}"
        result = await LineAdoptionConversationService(
            AdoptionDraftRepository(session, organization_id)
        ).apply_freetext_answers_to_locked_draft(draft=draft, extracted=extracted)
        job.status = "succeeded"
        job.failure_reason = failure_reason
        job.raw_ai_output = dict(extracted)
        job.validation_result = {
            "status": "valid" if failure_reason is None else "fallback",
            "result_state": result.state.value,
            "notification_status": "pending",
            "notification_attempt_count": 0,
        }
        job.completed_at = datetime.now(timezone.utc)
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None
        job.input_snapshot = None
        return ProfileExtractionOutcome(
            applied=True,
            actual_version=draft.interaction_version,
            next_job_id=result.ai_job_id,
        )


async def mark_profile_extraction_retry(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    organization_id: UUID,
    claim_token: str,
    failure_reason: str,
    countdown: int,
) -> None:
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
            )
            .with_for_update()
        )
        if job is None or job.status != "running" or job.claim_token != claim_token:
            return
        job.retry_count = (job.retry_count or 0) + 1
        job.status = "retry_wait"
        job.failure_reason = failure_reason[:500]
        job.available_at = datetime.now(timezone.utc) + timedelta(seconds=countdown)
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None


async def claim_profile_extraction_notification(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
) -> ProfileExtractionNotification | None:
    now = datetime.now(timezone.utc)
    stale_before_epoch = int(now.timestamp()) - get_worker_settings().celery_visibility_timeout
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
                AIProcessingJob.target_id == draft_id,
                AIProcessingJob.domain_version == expected_version,
                AIProcessingJob.status == "succeeded",
            )
            .with_for_update()
        )
        if job is None:
            return None
        validation = dict(job.validation_result or {})
        status = validation.get("notification_status")
        if status == "sending":
            claimed_at_epoch = int(validation.get("notification_claimed_at_epoch") or 0)
            if claimed_at_epoch > stale_before_epoch:
                return None
        elif status not in NOTIFICATION_CLAIMABLE:
            return None
        available_at = int(validation.get("notification_available_at_epoch") or 0)
        if status == "retry_wait" and available_at > int(now.timestamp()):
            return None
        attempt_count = int(validation.get("notification_attempt_count") or 0)
        if attempt_count >= get_worker_settings().celery_max_retries + 1:
            validation["notification_status"] = "exhausted"
            validation["notification_failure"] = "notification_retry_exhausted"
            job.validation_result = validation
            return None
        draft = await session.scalar(
            select(AdoptionDraft)
            .where(
                AdoptionDraft.id == draft_id,
                AdoptionDraft.organization_id == organization_id,
            )
            .with_for_update()
        )
        if (
            draft is None
            or draft.status != "active"
            or draft.interaction_version != expected_version + 1
            or draft.current_step != validation.get("result_state")
            or draft.path not in {path.value for path in AdoptionPath}
        ):
            validation["notification_status"] = "discarded"
            validation["notification_failure"] = "stale_domain_state"
            job.validation_result = validation
            return None
        line_user_id = await session.scalar(
            select(LineUserBinding.line_user_id).where(
                LineUserBinding.user_id == draft.adopter_user_id,
                LineUserBinding.status == "active",
            )
        )
        if not line_user_id:
            validation["notification_status"] = "skipped"
            validation["notification_failure"] = "recipient_unavailable"
            job.validation_result = validation
            return None
        validation["notification_status"] = "sending"
        validation["notification_claim_token"] = claim_token
        validation["notification_claimed_at_epoch"] = int(now.timestamp())
        validation["notification_attempt_count"] = attempt_count + 1
        validation.pop("notification_available_at_epoch", None)
        job.validation_result = validation
        return ProfileExtractionNotification(
            line_user_id=line_user_id,
            path=draft.path,
            answers=dict(draft.answers),
            state=AdoptionDraftState(draft.current_step),
            actual_version=draft.interaction_version,
        )


async def mark_profile_extraction_notification(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    organization_id: UUID,
    status: str,
    claim_token: str,
    failure_reason: str | None = None,
    countdown: int | None = None,
) -> None:
    if status not in {"sent", "retry_wait", "failed"}:
        raise ValueError("unsupported profile notification status")
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
                AIProcessingJob.status == "succeeded",
            )
            .with_for_update()
        )
        if job is None:
            return
        validation = dict(job.validation_result or {})
        if validation.get("notification_claim_token") != claim_token:
            return
        validation["notification_status"] = status
        if failure_reason:
            validation["notification_failure"] = failure_reason[:120]
        else:
            validation.pop("notification_failure", None)
        if countdown is not None:
            validation["notification_available_at_epoch"] = int(
                (datetime.now(timezone.utc) + timedelta(seconds=countdown)).timestamp()
            )
        else:
            validation.pop("notification_available_at_epoch", None)
        validation.pop("notification_claim_token", None)
        validation.pop("notification_claimed_at_epoch", None)
        job.validation_result = validation


def _validate_extracted(extracted: dict[str, str], *, path: AdoptionPath) -> None:
    if not isinstance(extracted, dict):
        raise MalformedAiResponse("invalid_profile_schema")
    _keys, valid_values = profile_extraction_contract(
        include_recommend_me_keys=path == AdoptionPath.RECOMMEND_ME
    )
    if set(extracted) - set(valid_values):
        raise MalformedAiResponse("unknown_profile_key")
    for key, value in extracted.items():
        if not isinstance(value, str):
            raise MalformedAiResponse("invalid_profile_value_type")
        if len(value) > 100:
            raise MalformedAiResponse("oversized_profile_value")
        if value not in valid_values[key]:
            raise MalformedAiResponse("invalid_profile_enum")


def _discard(job: AIProcessingJob, reason: str) -> None:
    job.status = "discarded"
    job.failure_reason = reason
    job.completed_at = datetime.now(timezone.utc)
    job.claim_token = None
    job.claimed_at = None
    job.claimed_by = None
    job.input_snapshot = None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
