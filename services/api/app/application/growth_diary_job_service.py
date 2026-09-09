from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.app.application.growth_diary_ai_analysis_service import (
    GrowthDiaryAiAnalysisResult,
)
from services.api.app.config.settings import get_worker_settings
from services.api.app.infrastructure.ai.gemini_client import MalformedAiResponse
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.growth_diary import GrowthDiaryEntry
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    OrganizationMembership,
)

JOB_TYPE = "growth_diary_analysis"
TARGET_TYPE = "growth_diary_entry"
CLAIMABLE = {"pending_enqueue", "enqueue_failed", "queued", "retry_wait"}
TERMINAL = {"succeeded", "failed", "discarded"}
ALERT_ROLES = {"STAFF", "SHELTER_ADMIN"}


@dataclass(frozen=True)
class GrowthDiarySnapshot:
    note: str | None
    animal_name: str
    photo_key: str | None
    photo_content_type: str | None
    retry_count: int
    skip_ai_reason: str | None = None


@dataclass(frozen=True)
class GrowthDiaryOutcome:
    applied: bool
    stale: bool = False
    actual_version: int | None = None


@dataclass(frozen=True)
class GrowthDiaryDelivery:
    delivery_id: str
    purpose: str
    user_id: UUID
    line_user_id: str
    mood: str | None
    adopter_reply: str | None
    staff_summary: str | None
    animal_name: str


async def claim_growth_diary_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    entry_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    worker_name: str,
) -> GrowthDiarySnapshot | None:
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
                AIProcessingJob.target_type == TARGET_TYPE,
                AIProcessingJob.target_id == entry_id,
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
        snapshot = _parse_snapshot(job)
        if snapshot is None:
            _discard(job, "invalid_input_snapshot")
            return None
        photo_keys = snapshot
        entry = await session.scalar(
            select(GrowthDiaryEntry)
            .where(
                GrowthDiaryEntry.id == entry_id,
                GrowthDiaryEntry.organization_id == organization_id,
            )
            .with_for_update()
        )
        if (
            entry is None
            or entry.content_version != expected_version
            or _entry_photo_keys(entry) != photo_keys
        ):
            _discard(job, "stale_domain_state")
            return None
        animal_name = await session.scalar(
            select(AdoptionInquiry.animal_name_snapshot).where(
                AdoptionInquiry.id == entry.inquiry_id,
                AdoptionInquiry.organization_id == organization_id,
                AdoptionInquiry.target_animal_id == entry.animal_id,
                AdoptionInquiry.adopter_user_id == entry.adopter_user_id,
            )
        )
        if animal_name is None:
            _discard(job, "invalid_growth_diary_source")
            entry.ai_analysis_status = "failed"
            entry.ai_content_version = expected_version
            entry.ai_analyzed_at = now
            return None
        if not entry.note and not photo_keys and skip_ai_reason is None:
            skip_ai_reason = "no_analyzable_content"
        entry.ai_analysis_status = "processing"
        entry.ai_content_version = expected_version
        job.status = "running"
        job.claim_token = claim_token
        job.claimed_by = worker_name[:120]
        job.claimed_at = now
        job.started_at = job.started_at or now
        job.available_at = None
        return GrowthDiarySnapshot(
            note=entry.note,
            animal_name=animal_name,
            photo_key=photo_keys[-1] if photo_keys else None,
            photo_content_type=entry.photo_content_type if photo_keys else None,
            retry_count=job.retry_count or 0,
            skip_ai_reason=skip_ai_reason,
        )


async def apply_growth_diary_result(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    entry_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
    result: GrowthDiaryAiAnalysisResult | None,
    failure_reason: str | None = None,
) -> GrowthDiaryOutcome:
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
                AIProcessingJob.target_type == TARGET_TYPE,
                AIProcessingJob.target_id == entry_id,
                AIProcessingJob.domain_version == expected_version,
            )
            .with_for_update()
        )
        entry = await session.scalar(
            select(GrowthDiaryEntry)
            .where(
                GrowthDiaryEntry.id == entry_id,
                GrowthDiaryEntry.organization_id == organization_id,
            )
            .with_for_update()
        )
        if job is None or job.status != "running" or job.claim_token != claim_token:
            return GrowthDiaryOutcome(applied=False)
        snapshot = _parse_snapshot(job)
        if (
            entry is None
            or entry.content_version != expected_version
            or snapshot is None
            or _entry_photo_keys(entry) != snapshot
        ):
            _discard(job, "stale_domain_state")
            return GrowthDiaryOutcome(
                applied=False,
                stale=True,
                actual_version=entry.content_version if entry is not None else None,
            )
        try:
            if result is not None:
                _validate_result(result)
        except MalformedAiResponse as exc:
            result = None
            failure_reason = failure_reason or f"malformed:{type(exc).__name__}"
        now = datetime.now(timezone.utc)
        entry.ai_content_version = expected_version
        entry.ai_analyzed_at = now
        _clear_ai_result(entry)
        if result is None:
            entry.ai_analysis_status = (
                "unconfigured" if failure_reason == "gemini_unconfigured" else "failed"
            )
        else:
            entry.ai_analysis_status = "succeeded"
            entry.ai_mood = result.mood
            entry.ai_reply = result.adopter_reply
            entry.ai_staff_summary = result.staff_summary
            entry.ai_provider = result.provider
            entry.ai_model_name = result.model_name
            entry.ai_model_version = result.model_version
            entry.ai_prompt_version = result.prompt_version
            entry.ai_output_schema_version = result.output_schema_version
            entry.ai_raw_output = result.raw_output
        staff_ids: list[UUID] = []
        if result is not None and result.mood == "concern":
            staff_ids = list(
                (
                    await session.scalars(
                        select(OrganizationMembership.user_id)
                        .where(
                            OrganizationMembership.organization_id == organization_id,
                            OrganizationMembership.role.in_(ALERT_ROLES),
                            OrganizationMembership.status == "active",
                        )
                        .distinct()
                    )
                ).all()
            )
        deliveries = [
            _delivery("adopter", entry.adopter_user_id),
            *[_delivery("staff", user_id) for user_id in staff_ids],
        ]
        job.status = "succeeded" if result is not None else "failed"
        job.failure_reason = failure_reason
        job.raw_ai_output = (
            {
                "mood": result.mood,
                "adopter_reply": result.adopter_reply,
                "staff_summary": result.staff_summary,
            }
            if result is not None
            else None
        )
        job.validation_result = {
            "status": "valid" if result is not None else "failed",
            "analysis_status": entry.ai_analysis_status,
            "notification_status": "pending",
            "deliveries": deliveries,
        }
        job.completed_at = now
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None
        job.input_snapshot = None
        return GrowthDiaryOutcome(applied=True, actual_version=entry.content_version)


async def mark_growth_diary_retry(
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
        job.status = "retry_wait"
        job.retry_count = (job.retry_count or 0) + 1
        job.failure_reason = failure_reason[:500]
        job.available_at = datetime.now(timezone.utc) + timedelta(seconds=countdown)
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None


async def claim_growth_diary_notifications(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    entry_id: UUID,
    organization_id: UUID,
    expected_version: int,
    claim_token: str,
) -> tuple[GrowthDiaryDelivery, ...]:
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
                AIProcessingJob.target_id == entry_id,
                AIProcessingJob.domain_version == expected_version,
                AIProcessingJob.status.in_(("succeeded", "failed")),
            )
            .with_for_update()
        )
        entry = await session.scalar(
            select(GrowthDiaryEntry)
            .where(
                GrowthDiaryEntry.id == entry_id,
                GrowthDiaryEntry.organization_id == organization_id,
            )
            .with_for_update()
        )
        if job is None:
            return ()
        validation = dict(job.validation_result or {})
        deliveries = [dict(item) for item in validation.get("deliveries", [])]
        if (
            entry is None
            or entry.content_version != expected_version
            or entry.ai_content_version != expected_version
        ):
            for item in deliveries:
                if item.get("status") not in {"sent", "skipped", "exhausted"}:
                    item["status"] = "discarded"
            validation["deliveries"] = deliveries
            validation["notification_status"] = "discarded"
            job.validation_result = validation
            return ()
        now = datetime.now(timezone.utc)
        stale_before = int(now.timestamp()) - get_worker_settings().celery_visibility_timeout
        max_attempts = get_worker_settings().celery_max_retries + 1
        candidate_ids: list[UUID] = []
        for item in deliveries:
            status = item.get("status")
            if status == "sending" and int(item.get("claimed_at_epoch") or 0) > stale_before:
                continue
            if status not in {"pending", "retry_wait", "failed", "sending"}:
                continue
            if int(item.get("available_at_epoch") or 0) > int(now.timestamp()):
                continue
            if int(item.get("attempt_count") or 0) >= max_attempts:
                item["status"] = "exhausted"
                continue
            try:
                candidate_ids.append(UUID(item["user_id"]))
            except (KeyError, TypeError, ValueError, AttributeError):
                item["status"] = "skipped"
        bindings = {
            user_id: line_user_id
            for user_id, line_user_id in (
                await session.execute(
                    select(LineUserBinding.user_id, LineUserBinding.line_user_id).where(
                        LineUserBinding.user_id.in_(candidate_ids),
                        LineUserBinding.status == "active",
                    )
                )
            ).all()
        }
        staff_ids = set(
            (
                await session.scalars(
                    select(OrganizationMembership.user_id).where(
                        OrganizationMembership.organization_id == organization_id,
                        OrganizationMembership.user_id.in_(candidate_ids),
                        OrganizationMembership.role.in_(ALERT_ROLES),
                        OrganizationMembership.status == "active",
                    )
                )
            ).all()
        )
        animal_name = (
            await session.scalar(
                select(AdoptionInquiry.animal_name_snapshot).where(
                    AdoptionInquiry.id == entry.inquiry_id,
                    AdoptionInquiry.organization_id == organization_id,
                )
            )
        ) or "毛孩"
        claimed: list[GrowthDiaryDelivery] = []
        for item in deliveries:
            status = item.get("status")
            if status == "sending" and int(item.get("claimed_at_epoch") or 0) > stale_before:
                continue
            if status not in {"pending", "retry_wait", "failed", "sending"}:
                continue
            if int(item.get("available_at_epoch") or 0) > int(now.timestamp()):
                continue
            try:
                user_id = UUID(item["user_id"])
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            purpose = item.get("purpose")
            authorized = (purpose == "adopter" and user_id == entry.adopter_user_id) or (
                purpose == "staff" and user_id in staff_ids
            )
            line_user_id = bindings.get(user_id)
            if not authorized or line_user_id is None:
                item["status"] = "skipped"
                continue
            item["status"] = "sending"
            item["claim_token"] = claim_token
            item["claimed_at_epoch"] = int(now.timestamp())
            item["attempt_count"] = int(item.get("attempt_count") or 0) + 1
            claimed.append(
                GrowthDiaryDelivery(
                    delivery_id=item["id"],
                    purpose=purpose,
                    user_id=user_id,
                    line_user_id=line_user_id,
                    mood=entry.ai_mood,
                    adopter_reply=entry.ai_reply,
                    staff_summary=entry.ai_staff_summary,
                    animal_name=animal_name,
                )
            )
        validation["deliveries"] = deliveries
        validation["notification_status"] = "sending" if claimed else _aggregate(deliveries)
        job.validation_result = validation
        return tuple(claimed)


async def mark_growth_diary_delivery(
    factory: async_sessionmaker[AsyncSession],
    *,
    job_id: UUID,
    organization_id: UUID,
    delivery_id: str,
    claim_token: str,
    status: str,
    failure_reason: str | None = None,
    countdown: int | None = None,
) -> None:
    if status not in {"sent", "retry_wait", "exhausted"}:
        raise ValueError("unsupported growth diary delivery status")
    async with factory() as session, session.begin():
        await set_organization_scope(session, organization_id)
        job = await session.scalar(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.job_type == JOB_TYPE,
                AIProcessingJob.status.in_(("succeeded", "failed")),
            )
            .with_for_update()
        )
        if job is None:
            return
        validation = dict(job.validation_result or {})
        deliveries = [dict(item) for item in validation.get("deliveries", [])]
        for item in deliveries:
            if item.get("id") != delivery_id or item.get("claim_token") != claim_token:
                continue
            item["status"] = status
            item.pop("claim_token", None)
            item.pop("claimed_at_epoch", None)
            if failure_reason:
                item["failure_reason"] = failure_reason[:120]
            else:
                item.pop("failure_reason", None)
            if countdown is not None:
                available = datetime.now(timezone.utc) + timedelta(seconds=countdown)
                item["available_at_epoch"] = int(available.timestamp())
                job.available_at = available
            else:
                item.pop("available_at_epoch", None)
            break
        validation["deliveries"] = deliveries
        validation["notification_status"] = _aggregate(deliveries)
        job.validation_result = validation


def _parse_snapshot(job: AIProcessingJob) -> tuple[str, ...] | None:
    snapshot = job.input_snapshot
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "content_version",
        "photo_keys",
        "schema_version",
        "source",
    }:
        return None
    keys = snapshot.get("photo_keys")
    if (
        snapshot.get("content_version") != job.domain_version
        or snapshot.get("schema_version") != "1"
        or snapshot.get("source") != "growth_diary_entry"
        or not isinstance(keys, list)
        or len(keys) > 8
        or not all(isinstance(key, str) and 0 < len(key) <= 500 for key in keys)
        or len(set(keys)) != len(keys)
    ):
        return None
    return tuple(keys)


def _entry_photo_keys(entry: GrowthDiaryEntry) -> tuple[str, ...]:
    return tuple(entry.photo_keys or ([] if entry.photo_key is None else [entry.photo_key]))


def _validate_result(result: GrowthDiaryAiAnalysisResult) -> None:
    if not isinstance(result.mood, str) or result.mood not in {
        "positive",
        "neutral",
        "concern",
    }:
        raise MalformedAiResponse("invalid_growth_diary_mood")
    if (
        not isinstance(result.adopter_reply, str)
        or not result.adopter_reply.strip()
        or len(result.adopter_reply) > 1000
    ):
        raise MalformedAiResponse("invalid_growth_diary_adopter_reply")
    if (
        not isinstance(result.staff_summary, str)
        or not result.staff_summary.strip()
        or len(result.staff_summary) > 1000
    ):
        raise MalformedAiResponse("invalid_growth_diary_staff_summary")
    for value, maximum in (
        (result.provider, 100),
        (result.model_name, 200),
        (result.model_version, 200),
        (result.prompt_version, 100),
        (result.output_schema_version, 100),
    ):
        if not isinstance(value, str) or not value or len(value) > maximum:
            raise MalformedAiResponse("invalid_growth_diary_provenance")


def _clear_ai_result(entry: GrowthDiaryEntry) -> None:
    entry.ai_mood = None
    entry.ai_reply = None
    entry.ai_staff_summary = None
    entry.ai_provider = None
    entry.ai_model_name = None
    entry.ai_model_version = None
    entry.ai_prompt_version = None
    entry.ai_output_schema_version = None
    entry.ai_raw_output = None


def _delivery(purpose: str, user_id: UUID) -> dict:
    return {
        "id": f"{purpose}:{user_id}",
        "purpose": purpose,
        "user_id": str(user_id),
        "status": "pending",
        "attempt_count": 0,
    }


def _aggregate(deliveries: list[dict]) -> str:
    statuses = {item.get("status") for item in deliveries}
    if statuses & {"sending"}:
        return "sending"
    if statuses & {"retry_wait", "failed"}:
        return "retry_wait"
    if statuses & {"pending"}:
        return "pending"
    if statuses <= {"skipped"}:
        return "skipped"
    if statuses <= {"sent", "skipped"}:
        return "sent"
    if statuses <= {"sent", "skipped", "exhausted"}:
        return "exhausted"
    return "discarded"


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
