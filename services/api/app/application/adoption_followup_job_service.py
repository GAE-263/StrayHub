from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.app.application.adoption_ai_analysis_service import (
    build_alternatives_prompt,
)
from services.api.app.config.settings import get_worker_settings
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiAnimalRecommendation,
    MalformedAiResponse,
)
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import LineUserBinding

JOB_TYPE = "adoption_followup_recommendations"
TARGET_TYPE = "adoption_draft"
CLAIMABLE = {"pending_enqueue", "enqueue_failed", "queued", "retry_wait"}
TERMINAL = {"succeeded", "failed", "discarded"}
NOTIFICATION_CLAIMABLE = {"pending", "retry_wait", "failed"}


@dataclass(frozen=True)
class FollowupCandidate:
    animal_id: UUID
    name: str
    shelter_number: str | None
    current_photo_key: str | None


@dataclass(frozen=True)
class FollowupSnapshot:
    prompt: str
    target_animal_id: UUID
    candidate_ids: tuple[UUID, ...]
    retry_count: int
    skip_ai_reason: str | None = None


@dataclass(frozen=True)
class FollowupOutcome:
    applied: bool
    stale: bool = False
    actual_version: int | None = None


@dataclass(frozen=True)
class FollowupNotification:
    line_user_id: str
    original: FollowupCandidate | None
    alternatives: tuple[tuple[FollowupCandidate, str], ...]
    state: AdoptionDraftState
    actual_version: int


async def claim_followup_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    worker_name: str,
) -> FollowupSnapshot | None:
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
            if _aware(job.available_at) > now:
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
        parsed = _parse_snapshot(job)
        if parsed is None:
            _discard(job, "invalid_input_snapshot")
            return None
        special_request, target_animal_id, candidate_ids = parsed
        if (
            draft is None
            or draft.status != "active"
            or draft.path != "specific_animal"
            or draft.current_step != AdoptionDraftState.AWAITING_AI_SUITABILITY.value
            or draft.interaction_version != expected_version
            or draft.ai_followup_target_animal_id != target_animal_id
        ):
            _discard(job, "stale_domain_state")
            return None
        candidates = await _load_available_animals(
            session, organization_id=organization_id, animal_ids=candidate_ids
        )
        ordered = [candidates[item] for item in candidate_ids if item in candidates]
        if not ordered and skip_ai_reason is None:
            skip_ai_reason = "no_valid_candidates"
        prompt = build_alternatives_prompt(special_request, ordered) if ordered else ""
        job.status = "running"
        job.claim_token = claim_token
        job.claimed_by = worker_name[:120]
        job.claimed_at = now
        job.started_at = job.started_at or now
        job.available_at = None
        job.validation_result = {"validated_candidate_ids": [str(animal.id) for animal in ordered]}
        return FollowupSnapshot(
            prompt=prompt,
            target_animal_id=target_animal_id,
            candidate_ids=tuple(animal.id for animal in ordered),
            retry_count=job.retry_count or 0,
            skip_ai_reason=skip_ai_reason,
        )


async def apply_followup_result(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    recommendations: list[GeminiAnimalRecommendation],
    failure_reason: str | None = None,
) -> FollowupOutcome:
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
            return FollowupOutcome(applied=False)
        parsed = _parse_snapshot(job)
        if parsed is None:
            _discard(job, "invalid_input_snapshot")
            return FollowupOutcome(applied=False)
        _special_request, target_animal_id, _snapshot_candidate_ids = parsed
        if (
            draft is None
            or draft.status != "active"
            or draft.current_step != AdoptionDraftState.AWAITING_AI_SUITABILITY.value
            or draft.interaction_version != expected_version
            or draft.ai_followup_target_animal_id != target_animal_id
        ):
            _discard(job, "stale_domain_state")
            return FollowupOutcome(
                applied=False,
                stale=True,
                actual_version=draft.interaction_version if draft is not None else None,
            )
        try:
            claim_validation = dict(job.validation_result or {})
            validated_ids = {
                UUID(value) for value in claim_validation.get("validated_candidate_ids", [])
            }
            _validate_recommendations(recommendations, allowed_ids=validated_ids)
        except (MalformedAiResponse, TypeError, ValueError, AttributeError) as exc:
            recommendations = []
            failure_reason = failure_reason or f"malformed:{type(exc).__name__}"
        requested_ids = [UUID(item.animal_id) for item in recommendations]
        all_ids = [target_animal_id, *requested_ids]
        available = await _load_available_animals(
            session,
            organization_id=organization_id,
            animal_ids=all_ids,
            for_update=True,
        )
        original = available.get(target_animal_id)
        valid_recommendations = [
            item
            for item in recommendations
            if UUID(item.animal_id) in available and UUID(item.animal_id) != target_animal_id
        ]
        candidate_ids: list[str] = []
        match_results: list[dict] = []
        if original is not None:
            candidate_ids.append(str(original.id))
            match_results.append({"animal_id": str(original.id), "reasons": ["你原本選定的毛孩"]})
        for item in valid_recommendations:
            candidate_ids.append(item.animal_id)
            match_results.append({"animal_id": item.animal_id, "reasons": [item.reason]})
        draft.ai_followup_target_animal_id = None
        draft.candidate_match_ids = candidate_ids
        draft.match_results = match_results
        draft.current_step = (
            AdoptionDraftState.SELECTING_ALTERNATIVE_ANIMAL.value
            if candidate_ids
            else AdoptionDraftState.AWAITING_ADOPTER_NAME.value
        )
        draft.interaction_version += 1
        draft.last_interaction_at = datetime.now(timezone.utc)
        job.status = "succeeded"
        job.failure_reason = failure_reason
        job.raw_ai_output = {
            "recommendations": [
                {"animal_id": item.animal_id, "reason": item.reason}
                for item in valid_recommendations
            ]
        }
        job.validation_result = {
            "status": "valid" if failure_reason is None else "fallback",
            "result_state": draft.current_step,
            "notification_status": "pending",
            "notification_attempt_count": 0,
        }
        job.completed_at = datetime.now(timezone.utc)
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None
        job.input_snapshot = None
        return FollowupOutcome(applied=True, actual_version=draft.interaction_version)


async def mark_followup_retry(
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


async def claim_followup_notification(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
) -> FollowupNotification | None:
    now = datetime.now(timezone.utc)
    stale_before = int(now.timestamp()) - get_worker_settings().celery_visibility_timeout
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
            if int(validation.get("notification_claimed_at_epoch") or 0) > stale_before:
                return None
        elif status not in NOTIFICATION_CLAIMABLE:
            return None
        if status == "retry_wait" and int(
            validation.get("notification_available_at_epoch") or 0
        ) > int(now.timestamp()):
            return None
        attempts = int(validation.get("notification_attempt_count") or 0)
        if attempts >= get_worker_settings().celery_max_retries + 1:
            validation["notification_status"] = "exhausted"
            job.validation_result = validation
            return None
        draft = await session.scalar(
            select(AdoptionDraft).where(
                AdoptionDraft.id == draft_id,
                AdoptionDraft.organization_id == organization_id,
            )
        )
        if (
            draft is None
            or draft.status != "active"
            or draft.interaction_version != expected_version + 1
            or draft.current_step != validation.get("result_state")
        ):
            validation["notification_status"] = "discarded"
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
            job.validation_result = validation
            return None
        ids = [UUID(value) for value in draft.candidate_match_ids or []]
        animals = await _load_available_animals(
            session, organization_id=organization_id, animal_ids=ids
        )
        output = job.raw_ai_output if isinstance(job.raw_ai_output, dict) else {}
        reasons = {
            item.get("animal_id"): item.get("reason")
            for item in output.get("recommendations", [])
            if isinstance(item, dict)
        }
        original_id = ids[0] if ids and str(ids[0]) not in reasons else None
        original = _candidate(animals[original_id]) if original_id in animals else None
        alternatives = tuple(
            (_candidate(animals[item]), str(reasons[str(item)]))
            for item in ids
            if item in animals and str(item) in reasons
        )
        validation["notification_status"] = "sending"
        validation["notification_claim_token"] = claim_token
        validation["notification_claimed_at_epoch"] = int(now.timestamp())
        validation["notification_attempt_count"] = attempts + 1
        validation.pop("notification_available_at_epoch", None)
        job.validation_result = validation
        return FollowupNotification(
            line_user_id=line_user_id,
            original=original,
            alternatives=alternatives,
            state=AdoptionDraftState(draft.current_step),
            actual_version=draft.interaction_version,
        )


async def mark_followup_notification(
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
        raise ValueError("unsupported followup notification status")
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


async def _load_available_animals(
    session: AsyncSession,
    *,
    organization_id: UUID,
    animal_ids: list[UUID] | tuple[UUID, ...],
    for_update: bool = False,
) -> dict[UUID, Animal]:
    if not animal_ids:
        return {}
    statement = select(Animal).where(
        Animal.organization_id == organization_id,
        Animal.id.in_(animal_ids),
        Animal.status == "active",
        Animal.is_adoptable.is_(True),
    )
    if for_update:
        statement = statement.with_for_update()
    animals = list((await session.scalars(statement)).all())
    return {animal.id: animal for animal in animals}


def _parse_snapshot(job: AIProcessingJob) -> tuple[str, UUID, tuple[UUID, ...]] | None:
    snapshot = job.input_snapshot
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "special_request",
        "target_animal_id",
        "candidate_ids",
        "schema_version",
        "source",
    }:
        return None
    special_request = snapshot.get("special_request")
    raw_ids = snapshot.get("candidate_ids")
    if (
        not isinstance(special_request, str)
        or not special_request.strip()
        or len(special_request) > 2000
        or not isinstance(raw_ids, list)
        or len(raw_ids) > 30
        or snapshot.get("schema_version") != "1"
        or snapshot.get("source") != "line_free_text"
    ):
        return None
    try:
        target_id = UUID(str(snapshot.get("target_animal_id")))
        candidate_ids = tuple(UUID(value) for value in raw_ids)
    except (TypeError, ValueError, AttributeError):
        return None
    if len(set(candidate_ids)) != len(candidate_ids) or target_id in candidate_ids:
        return None
    return special_request.strip(), target_id, candidate_ids


def _validate_recommendations(
    recommendations: list[GeminiAnimalRecommendation], *, allowed_ids: set[UUID]
) -> None:
    if not isinstance(recommendations, list) or len(recommendations) > 3:
        raise MalformedAiResponse("invalid_followup_count")
    seen: set[UUID] = set()
    for item in recommendations:
        if not isinstance(item, GeminiAnimalRecommendation):
            raise MalformedAiResponse("invalid_followup_item")
        try:
            animal_id = UUID(item.animal_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise MalformedAiResponse("invalid_followup_animal_id") from exc
        if animal_id not in allowed_ids or animal_id in seen:
            raise MalformedAiResponse("invalid_followup_animal_id")
        if not item.reason.strip() or len(item.reason) > 100:
            raise MalformedAiResponse("invalid_followup_reason")
        seen.add(animal_id)


def _candidate(animal: Animal) -> FollowupCandidate:
    return FollowupCandidate(
        animal_id=animal.id,
        name=animal.name,
        shelter_number=animal.shelter_number,
        current_photo_key=animal.current_photo_key,
    )


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
