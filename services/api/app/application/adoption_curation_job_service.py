from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.app.application.adoption_ai_analysis_service import (
    build_recommendation_prompt,
)
from services.api.app.config.settings import get_worker_settings
from services.api.app.domain.line_adoption_state import (
    MATCH_PREFERENCE_KEYS,
    AdoptionDraftState,
)
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiRankedRecommendation,
    MalformedAiResponse,
)
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import LineUserBinding

JOB_TYPE = "adoption_recommendation_curation"
TARGET_TYPE = "adoption_draft"
CLAIMABLE = {"pending_enqueue", "enqueue_failed", "queued", "retry_wait"}
TERMINAL = {"succeeded", "failed", "discarded"}
NOTIFICATION_CLAIMABLE = {"pending", "retry_wait", "failed"}


@dataclass(frozen=True)
class CurationSnapshot:
    prompt: str
    candidate_ids: tuple[UUID, ...]
    retry_count: int
    skip_ai_reason: str | None = None


@dataclass(frozen=True)
class CurationOutcome:
    applied: bool
    stale: bool = False
    actual_version: int | None = None


@dataclass(frozen=True)
class CuratedCandidate:
    animal_id: UUID
    name: str
    shelter_number: str | None
    current_photo_key: str | None
    score: int | float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CurationNotification:
    line_user_id: str
    candidates: tuple[CuratedCandidate, ...]
    actual_version: int


async def claim_curation_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    worker_name: str,
) -> CurationSnapshot | None:
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
        parsed = _parse_snapshot(job)
        if parsed is None:
            _discard(job, "invalid_input_snapshot")
            return None
        candidate_ids, _rule_results, preferences = parsed
        draft = await session.scalar(
            select(AdoptionDraft)
            .where(
                AdoptionDraft.id == draft_id,
                AdoptionDraft.organization_id == organization_id,
            )
            .with_for_update()
        )
        current_candidate_ids = _draft_candidate_ids(draft)
        if (
            draft is None
            or draft.status != "active"
            or draft.path != "recommend_me"
            or draft.current_step != AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS.value
            or draft.interaction_version != expected_version
            or current_candidate_ids != candidate_ids
        ):
            _discard(job, "stale_domain_state")
            return None
        available = await _load_available_animals(
            session, organization_id=organization_id, animal_ids=candidate_ids
        )
        ordered = [available[item] for item in candidate_ids if item in available]
        if not ordered and skip_ai_reason is None:
            skip_ai_reason = "no_valid_candidates"
        prompt = build_recommendation_prompt(preferences, ordered) if ordered else ""
        job.status = "running"
        job.claim_token = claim_token
        job.claimed_by = worker_name[:120]
        job.claimed_at = now
        job.started_at = job.started_at or now
        job.available_at = None
        job.validation_result = {"validated_candidate_ids": [str(animal.id) for animal in ordered]}
        return CurationSnapshot(
            prompt=prompt,
            candidate_ids=tuple(animal.id for animal in ordered),
            retry_count=job.retry_count or 0,
            skip_ai_reason=skip_ai_reason,
        )


async def apply_curation_result(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    recommendations: list[GeminiRankedRecommendation],
    failure_reason: str | None = None,
) -> CurationOutcome:
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
            return CurationOutcome(applied=False)
        parsed = _parse_snapshot(job)
        if parsed is None:
            _discard(job, "invalid_input_snapshot")
            return CurationOutcome(applied=False)
        snapshot_ids, rule_results, _preferences = parsed
        current_candidate_ids = _draft_candidate_ids(draft)
        if (
            draft is None
            or draft.status != "active"
            or draft.path != "recommend_me"
            or draft.current_step != AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS.value
            or draft.interaction_version != expected_version
            or current_candidate_ids != snapshot_ids
        ):
            _discard(job, "stale_domain_state")
            return CurationOutcome(
                applied=False,
                stale=True,
                actual_version=draft.interaction_version if draft is not None else None,
            )
        try:
            validation = dict(job.validation_result or {})
            allowed_ids = {UUID(value) for value in validation.get("validated_candidate_ids", [])}
            _validate_recommendations(recommendations, allowed_ids=allowed_ids)
        except (MalformedAiResponse, TypeError, ValueError, AttributeError) as exc:
            recommendations = []
            failure_reason = failure_reason or f"malformed:{type(exc).__name__}"
        available = await _load_available_animals(
            session,
            organization_id=organization_id,
            animal_ids=snapshot_ids,
            for_update=True,
        )
        valid_ranked = [item for item in recommendations if UUID(item.animal_id) in available]
        rule_by_id = {item["animal_id"]: item for item in rule_results}
        if valid_ranked:
            match_results = [
                {
                    "animal_id": item.animal_id,
                    "score": item.score,
                    "reasons": [item.explanation],
                }
                for item in valid_ranked
            ]
        else:
            fallback_ids = [item for item in snapshot_ids if item in available]
            match_results = [rule_by_id[str(item)] for item in fallback_ids]
            if recommendations:
                failure_reason = failure_reason or "curated_candidates_unavailable"
        draft.candidate_match_ids = [item["animal_id"] for item in match_results]
        draft.match_results = match_results
        draft.current_step = AdoptionDraftState.SELECTING_MATCHED_ANIMAL.value
        draft.interaction_version += 1
        draft.last_interaction_at = datetime.now(timezone.utc)
        job.status = "succeeded"
        job.failure_reason = failure_reason
        job.raw_ai_output = {"recommendations": match_results}
        job.validation_result = {
            "status": "valid" if valid_ranked and failure_reason is None else "fallback",
            "result_state": draft.current_step,
            "notification_status": "pending",
            "notification_attempt_count": 0,
        }
        job.completed_at = datetime.now(timezone.utc)
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None
        job.input_snapshot = None
        return CurationOutcome(applied=True, actual_version=draft.interaction_version)


async def mark_curation_retry(
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


async def claim_curation_notification(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
) -> CurationNotification | None:
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
        available = await _load_available_animals(
            session, organization_id=organization_id, animal_ids=ids
        )
        result_by_id = {
            item.get("animal_id"): item
            for item in draft.match_results or []
            if isinstance(item, dict)
        }
        candidates = tuple(
            CuratedCandidate(
                animal_id=animal_id,
                name=available[animal_id].name,
                shelter_number=available[animal_id].shelter_number,
                current_photo_key=available[animal_id].current_photo_key,
                score=result_by_id.get(str(animal_id), {}).get("score"),
                reasons=tuple(result_by_id.get(str(animal_id), {}).get("reasons") or []),
            )
            for animal_id in ids
            if animal_id in available
        )
        validation["notification_status"] = "sending"
        validation["notification_claim_token"] = claim_token
        validation["notification_claimed_at_epoch"] = int(now.timestamp())
        validation["notification_attempt_count"] = attempts + 1
        validation.pop("notification_available_at_epoch", None)
        job.validation_result = validation
        return CurationNotification(
            line_user_id=line_user_id,
            candidates=candidates,
            actual_version=draft.interaction_version,
        )


async def mark_curation_notification(
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
        raise ValueError("unsupported curation notification status")
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


def _parse_snapshot(
    job: AIProcessingJob,
) -> tuple[tuple[UUID, ...], list[dict], dict[str, str]] | None:
    snapshot = job.input_snapshot
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "candidate_ids",
        "rule_results",
        "preferences",
        "schema_version",
        "source",
    }:
        return None
    raw_ids = snapshot.get("candidate_ids")
    rule_results = snapshot.get("rule_results")
    preferences = snapshot.get("preferences")
    if (
        not isinstance(raw_ids, list)
        or not 1 <= len(raw_ids) <= 5
        or not isinstance(rule_results, list)
        or len(rule_results) != len(raw_ids)
        or not isinstance(preferences, dict)
        or set(preferences) != set(MATCH_PREFERENCE_KEYS)
        or not all(isinstance(value, str) and len(value) <= 100 for value in preferences.values())
        or snapshot.get("schema_version") != "1"
        or snapshot.get("source") != "rule_based_matching"
    ):
        return None
    try:
        ids = tuple(UUID(value) for value in raw_ids)
    except (TypeError, ValueError, AttributeError):
        return None
    if len(set(ids)) != len(ids):
        return None
    normalized: list[dict] = []
    for expected_id, item in zip(ids, rule_results, strict=True):
        if not isinstance(item, dict) or set(item) != {"animal_id", "score", "reasons"}:
            return None
        score = item["score"]
        reasons = item["reasons"]
        if (
            item["animal_id"] != str(expected_id)
            or (
                score is not None
                and (isinstance(score, bool) or not isinstance(score, int | float))
            )
            or not isinstance(reasons, list)
            or not all(isinstance(reason, str) and len(reason) <= 200 for reason in reasons)
        ):
            return None
        normalized.append({"animal_id": str(expected_id), "score": score, "reasons": list(reasons)})
    return ids, normalized, dict(preferences)


def _validate_recommendations(
    recommendations: list[GeminiRankedRecommendation], *, allowed_ids: set[UUID]
) -> None:
    if not isinstance(recommendations, list) or len(recommendations) > 5:
        raise MalformedAiResponse("invalid_curation_count")
    seen: set[UUID] = set()
    for item in recommendations:
        if not isinstance(item, GeminiRankedRecommendation):
            raise MalformedAiResponse("invalid_curation_item")
        try:
            animal_id = UUID(item.animal_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise MalformedAiResponse("invalid_curation_animal_id") from exc
        if animal_id not in allowed_ids or animal_id in seen:
            raise MalformedAiResponse("invalid_curation_animal_id")
        if isinstance(item.score, bool) or not 0 <= item.score <= 100:
            raise MalformedAiResponse("invalid_curation_score")
        if not item.explanation.strip() or len(item.explanation) > 200:
            raise MalformedAiResponse("invalid_curation_explanation")
        seen.add(animal_id)


def _draft_candidate_ids(draft: AdoptionDraft | None) -> tuple[UUID, ...] | None:
    if draft is None or not isinstance(draft.candidate_match_ids, list):
        return None
    try:
        return tuple(UUID(value) for value in draft.candidate_match_ids)
    except (TypeError, ValueError, AttributeError):
        return None


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
