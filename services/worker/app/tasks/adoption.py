from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from celery import Task
from sqlalchemy import select

from services.api.app.application.adoption_suitability_job_service import (
    SuitabilityOutcome,
    apply_suitability_result,
    claim_suitability_job,
    mark_suitability_notification,
    mark_suitability_retry,
)
from services.api.app.application.line_adoption_flex import (
    AiSuitabilityCard,
    build_ai_suitability_card,
    build_info_card,
)
from services.api.app.application.media_access import issue_adoption_photo_token
from services.api.app.config.settings import get_worker_settings
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiClient,
    PermanentAiError,
    TransientAiError,
)
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.observability.logging import get_logger
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.identity import LineUserBinding
from services.worker.app.celery_runtime import runtime

logger = get_logger(__name__)


def _countdown(retries: int, maximum: int) -> int:
    return min(5 * (2**retries), maximum)


@celery_app.task(bind=True, name="adoption.analyze_suitability")
def analyze_suitability(
    self: Task,
    *,
    job_id: str,
    resource_id: str,
    organization_id: str,
    expected_version: int,
) -> str:
    job_uuid = UUID(job_id)
    draft_uuid = UUID(resource_id)
    organization_uuid = UUID(organization_id)
    claim_token = str(self.request.id or job_uuid)
    worker_name = str(self.request.hostname or "celery-worker")
    snapshot = runtime.run(
        lambda factory: claim_suitability_job(
            factory,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            worker_name=worker_name,
        )
    )
    if snapshot is None:
        return "discarded_or_duplicate"

    settings = get_worker_settings()
    result = None
    failure_reason = None
    gemini = None
    try:
        if settings.gemini_service_account_path or settings.gemini_api_key:
            gemini = GeminiClient(
                model_name=settings.gemini_model_name,
                api_key=settings.gemini_api_key,
                service_account_path=settings.gemini_service_account_path,
                location=settings.gemini_vertex_location,
                timeout_seconds=min(20.0, float(settings.celery_task_soft_time_limit - 1)),
            )
            result = runtime.run(
                lambda _factory: gemini.analyze_suitability_strict(snapshot.prompt)
            )
        else:
            failure_reason = "gemini_unconfigured"
    except TransientAiError as exc:
        if self.request.retries < settings.celery_max_retries:
            countdown = _countdown(self.request.retries, settings.celery_retry_backoff_max)
            failure_reason = str(exc)
            runtime.run(
                lambda factory: mark_suitability_retry(
                    factory,
                    job_id=job_uuid,
                    organization_id=organization_uuid,
                    claim_token=claim_token,
                    failure_reason=failure_reason,
                    countdown=countdown,
                )
            )
            raise self.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.celery_max_retries,
            ) from exc
        failure_reason = f"retry_exhausted:{type(exc).__name__}"
    except PermanentAiError as exc:
        failure_reason = f"permanent:{type(exc).__name__}"
    finally:
        if gemini is not None:
            runtime.run(lambda _factory: gemini.aclose())

    outcome = runtime.run(
        lambda factory: apply_suitability_result(
            factory,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            snapshot=snapshot,
            result=result,
            failure_reason=failure_reason,
        )
    )
    if not outcome.applied:
        return "stale" if outcome.stale else "duplicate"
    try:
        runtime.run(
            lambda factory: _push_suitability_result(
                factory,
                organization_id=organization_uuid,
                draft_id=draft_uuid,
                job_id=job_uuid,
                outcome=outcome,
            )
        )
    except Exception as exc:
        failure_type = type(exc).__name__
        runtime.run(
            lambda factory: mark_suitability_notification(
                factory,
                job_id=job_uuid,
                organization_id=organization_uuid,
                status="failed",
                failure_reason=failure_type,
            )
        )
        logger.exception(
            "adoption_suitability_notification_failed",
            extra={
                "job_id": job_id,
                "organization_id": organization_id,
                "resource_id": resource_id,
            },
        )
    else:
        runtime.run(
            lambda factory: mark_suitability_notification(
                factory,
                job_id=job_uuid,
                organization_id=organization_uuid,
                status="sent",
            )
        )
    return "succeeded"


async def _push_suitability_result(
    factory,
    *,
    organization_id: UUID,
    draft_id: UUID,
    job_id: UUID,
    outcome: SuitabilityOutcome,
) -> None:
    async with factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.get(AIProcessingJob, job_id)
            if job is None or job.organization_id != organization_id:
                return
            from services.api.app.persistence.models.adoption_draft import AdoptionDraft

            draft = await session.get(AdoptionDraft, draft_id)
            if draft is None or draft.organization_id != organization_id:
                return
            line_user_id = await session.scalar(
                select(LineUserBinding.line_user_id).where(
                    LineUserBinding.user_id == draft.adopter_user_id,
                    LineUserBinding.status == "active",
                )
            )
    if not line_user_id or outcome.snapshot is None:
        return
    snapshot = outcome.snapshot
    messages: list[dict] = []
    if outcome.score is not None and outcome.explanation is not None:
        photo_url = None
        base_url = get_worker_settings().web_public_base_url.strip().rstrip("/")
        if base_url.startswith("https://") and snapshot.current_photo_key:
            token = issue_adoption_photo_token(
                organization_id=organization_id,
                animal_id=snapshot.animal_id,
                object_key=snapshot.current_photo_key,
                ttl_seconds=300,
            )
            photo_url = (
                f"{base_url}/v1/public/adoption/animals/{snapshot.animal_id}/photo?token={token}"
            )
        messages.append(
            build_ai_suitability_card(
                AiSuitabilityCard(
                    animal_id=str(snapshot.animal_id),
                    name=snapshot.animal_name,
                    shelter_number=snapshot.shelter_number,
                    photo_url=photo_url,
                    score=outcome.score,
                    explanation=outcome.explanation,
                )
            )
        )
    else:
        messages.append(
            {
                "type": "text",
                "text": "AI 適配度分析暫時無法使用，不過還是可以繼續留下聯絡方式 🐾",
            }
        )
    if outcome.asks_followup:
        messages.append(
            {
                "type": "text",
                "text": (
                    "如果不介意，可以告訴我們你對這隻毛孩的期待或特殊需求嗎？"
                    "想要母狗、個性安靜的孩子都可以直接打字告訴我們 🐾"
                ),
            }
        )
    else:
        messages.append(
            build_info_card("請留下您的姓名 🧑‍🤝‍🧑", accent_index=1, body="請直接輸入姓名")
        )
    async with httpx.AsyncClient(timeout=10) as client:
        await LineMessagingApiAdapter(client=client).push(
            to_user_id=line_user_id,
            messages=messages,
            retry_key=str(uuid5(NAMESPACE_URL, f"strayhub:{job_id}:adopter-suitability")),
        )
