from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.app.application.adoption_ai_analysis_service import build_suitability_prompt
from services.api.app.config.settings import get_worker_settings
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.infrastructure.ai.gemini_client import GeminiSuitabilityResult
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.animal import Animal

JOB_TYPE = "adoption_suitability"
TARGET_TYPE = "adoption_draft"
CLAIMABLE = {"pending_enqueue", "enqueue_failed", "queued", "retry_wait"}
TERMINAL = {"succeeded", "failed", "discarded"}


@dataclass(frozen=True)
class SuitabilitySnapshot:
    prompt: str
    animal_id: UUID
    animal_name: str
    shelter_number: str | None
    current_photo_key: str | None


@dataclass(frozen=True)
class SuitabilityOutcome:
    applied: bool
    stale: bool = False
    score: int | None = None
    explanation: str | None = None
    asks_followup: bool = False
    snapshot: SuitabilitySnapshot | None = None


async def claim_suitability_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    worker_name: str,
) -> SuitabilitySnapshot | None:
    async with factory() as session:
        async with session.begin():
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
            if job.status == "running" and job.claim_token != claim_token:
                stale_before = datetime.now(timezone.utc) - timedelta(
                    seconds=get_worker_settings().celery_visibility_timeout
                )
                if job.claimed_at is None or job.claimed_at >= stale_before:
                    return None
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
                or draft.current_step != AdoptionDraftState.AWAITING_AI_SUITABILITY.value
                or draft.interaction_version != expected_version
                or draft.target_animal_id is None
            ):
                _discard(job, "stale_domain_state")
                return None
            animal = await session.scalar(
                select(Animal).where(
                    Animal.id == draft.target_animal_id,
                    Animal.organization_id == organization_id,
                    Animal.status == "active",
                    Animal.is_adoptable.is_(True),
                )
            )
            if animal is None:
                _discard(job, "target_animal_unavailable")
                return None
            now = datetime.now(timezone.utc)
            job.status = "running"
            job.claim_token = claim_token
            job.claimed_by = worker_name[:120]
            job.claimed_at = now
            job.started_at = job.started_at or now
            return SuitabilitySnapshot(
                prompt=build_suitability_prompt(dict(draft.answers), animal),
                animal_id=animal.id,
                animal_name=animal.name,
                shelter_number=animal.shelter_number,
                current_photo_key=animal.current_photo_key,
            )


async def apply_suitability_result(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    snapshot: SuitabilitySnapshot,
    result: GeminiSuitabilityResult | None,
    failure_reason: str | None = None,
) -> SuitabilityOutcome:
    async with factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(
                select(AIProcessingJob)
                .where(
                    AIProcessingJob.id == job_id,
                    AIProcessingJob.organization_id == organization_id,
                    AIProcessingJob.job_type == JOB_TYPE,
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
            if job is None or job.claim_token != claim_token or job.status != "running":
                return SuitabilityOutcome(applied=False)
            if (
                draft is None
                or draft.status != "active"
                or draft.current_step != AdoptionDraftState.AWAITING_AI_SUITABILITY.value
                or draft.interaction_version != expected_version
            ):
                _discard(job, "stale_domain_state")
                return SuitabilityOutcome(applied=False, stale=True)
            asks_followup = result is not None and result.score < 60
            if result is not None:
                draft.ai_suitability_score = result.score
                draft.ai_suitability_explanation = result.explanation
            if asks_followup:
                draft.ai_followup_target_animal_id = snapshot.animal_id
            else:
                draft.current_step = AdoptionDraftState.AWAITING_ADOPTER_NAME.value
            draft.interaction_version += 1
            draft.last_interaction_at = datetime.now(timezone.utc)
            job.status = "succeeded"
            job.failure_reason = failure_reason
            job.validation_result = {
                "status": "valid" if result is not None else "fallback",
                "notification_status": "pending",
            }
            job.raw_ai_output = (
                {"score": result.score, "explanation": result.explanation}
                if result is not None
                else None
            )
            job.completed_at = datetime.now(timezone.utc)
            job.claim_token = None
            job.claimed_at = None
            job.claimed_by = None
            job.input_snapshot = None
            return SuitabilityOutcome(
                applied=True,
                score=result.score if result is not None else None,
                explanation=result.explanation if result is not None else None,
                asks_followup=asks_followup,
                snapshot=snapshot,
            )


async def mark_suitability_retry(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    organization_id: UUID,
    claim_token: str,
    failure_reason: str,
    countdown: int,
) -> None:
    async with factory() as session:
        async with session.begin():
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


async def mark_suitability_notification(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    organization_id: UUID,
    status: str,
    failure_reason: str | None = None,
) -> None:
    if status not in {"sent", "failed"}:
        raise ValueError("unsupported suitability notification status")
    async with factory() as session:
        async with session.begin():
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
            validation["notification_status"] = status
            if failure_reason:
                validation["notification_failure"] = failure_reason[:120]
            else:
                validation.pop("notification_failure", None)
            job.validation_result = validation


def _discard(job: AIProcessingJob, reason: str) -> None:
    job.status = "discarded"
    job.failure_reason = reason
    job.completed_at = datetime.now(timezone.utc)
    job.claim_token = None
    job.claimed_at = None
    job.claimed_by = None
    job.input_snapshot = None
