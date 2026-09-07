from __future__ import annotations

import time
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from billiard.exceptions import SoftTimeLimitExceeded
from celery import Task

from services.api.app.application.adoption_ai_analysis_service import (
    build_profile_summary_rows,
)
from services.api.app.application.adoption_curation_job_service import (
    CuratedCandidate,
    CurationNotification,
    apply_curation_result,
    claim_curation_job,
    claim_curation_notification,
    mark_curation_notification,
    mark_curation_retry,
)
from services.api.app.application.adoption_followup_job_service import (
    FollowupCandidate,
    FollowupNotification,
    apply_followup_result,
    claim_followup_job,
    claim_followup_notification,
    mark_followup_notification,
    mark_followup_retry,
)
from services.api.app.application.adoption_profile_extraction_job_service import (
    ProfileExtractionNotification,
    apply_profile_extraction_result,
    claim_profile_extraction_job,
    claim_profile_extraction_notification,
    mark_profile_extraction_notification,
    mark_profile_extraction_retry,
)
from services.api.app.application.adoption_suitability_job_service import (
    SuitabilityNotification,
    SuitabilityOutcome,
    apply_suitability_result,
    claim_suitability_job,
    claim_suitability_notification,
    mark_suitability_notification,
    mark_suitability_retry,
)
from services.api.app.application.celery_job_dispatch import dispatch_ai_job
from services.api.app.application.line_adoption_flex import (
    AiSuitabilityCard,
    MatchReportCard,
    build_ai_suitability_card,
    build_info_card,
    build_match_report,
)
from services.api.app.application.media_access import issue_adoption_photo_token
from services.api.app.config.settings import get_worker_settings
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiClient,
    PermanentAiError,
    TransientAiError,
)
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.observability.logging import get_logger
from services.worker.app.celery_runtime import runtime

logger = get_logger(__name__)


def _countdown(retries: int, maximum: int) -> int:
    return min(5 * (2**retries), maximum)


@celery_app.task(bind=True, name="adoption.curate_recommendations")
def curate_recommendations(
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
    started = time.monotonic()
    snapshot = runtime.run(
        lambda factory: claim_curation_job(
            factory,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            worker_name=str(self.request.hostname or "celery-worker"),
        )
    )
    if snapshot is None:
        return _deliver_curation_notification(
            self,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            started=started,
        )
    settings = get_worker_settings()
    recommendations = []
    failure_reason = snapshot.skip_ai_reason
    gemini = None
    try:
        if snapshot.skip_ai_reason is None and (
            settings.gemini_service_account_path or settings.gemini_api_key
        ):
            gemini = GeminiClient(
                model_name=settings.gemini_model_name,
                api_key=settings.gemini_api_key,
                service_account_path=settings.gemini_service_account_path,
                location=settings.gemini_vertex_location,
                timeout_seconds=max(
                    0.25,
                    min(20.0, float(settings.celery_task_soft_time_limit - 1)),
                ),
            )
            recommendations = runtime.run(
                lambda _factory: gemini.rank_recommendations_strict(
                    snapshot.prompt,
                    valid_animal_ids={str(item) for item in snapshot.candidate_ids},
                )
            )
        elif snapshot.skip_ai_reason is None:
            failure_reason = "gemini_unconfigured"
    except (TransientAiError, SoftTimeLimitExceeded) as exc:
        if snapshot.retry_count < settings.celery_max_retries:
            countdown = _countdown(snapshot.retry_count, settings.celery_retry_backoff_max)
            failure_type = type(exc).__name__
            runtime.run(
                lambda factory: mark_curation_retry(
                    factory,
                    job_id=job_uuid,
                    organization_id=organization_uuid,
                    claim_token=claim_token,
                    failure_reason=failure_type,
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
        lambda factory: apply_curation_result(
            factory,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            recommendations=recommendations,
            failure_reason=failure_reason,
        )
    )
    if not outcome.applied:
        logger.info(
            "adoption_curation_not_applied",
            extra={
                "job_id": job_id,
                "organization_id": organization_id,
                "draft_id": resource_id,
                "expected_version": expected_version,
                "actual_version": outcome.actual_version,
                "job_type": "adoption_recommendation_curation",
                "stale_discard": outcome.stale,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return "stale" if outcome.stale else "duplicate"
    return _deliver_curation_notification(
        self,
        job_id=job_uuid,
        draft_id=draft_uuid,
        organization_id=organization_uuid,
        expected_version=expected_version,
        started=started,
    )


def _deliver_curation_notification(
    task: Task,
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    started: float,
) -> str:
    settings = get_worker_settings()
    notification_token = str(uuid4())
    notification = runtime.run(
        lambda factory: claim_curation_notification(
            factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=expected_version,
            claim_token=notification_token,
        )
    )
    if notification is None:
        return "discarded_or_duplicate"
    try:
        runtime.run(
            lambda _factory: _push_curation_result(
                organization_id=organization_id,
                job_id=job_id,
                notification=notification,
            )
        )
    except Exception as exc:
        failure_type = type(exc).__name__
        if task.request.retries < settings.celery_max_retries:
            countdown = _countdown(task.request.retries, settings.celery_retry_backoff_max)
            runtime.run(
                lambda factory: mark_curation_notification(
                    factory,
                    job_id=job_id,
                    organization_id=organization_id,
                    status="retry_wait",
                    claim_token=notification_token,
                    failure_reason=failure_type,
                    countdown=countdown,
                )
            )
            raise task.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.celery_max_retries,
            ) from exc
        runtime.run(
            lambda factory: mark_curation_notification(
                factory,
                job_id=job_id,
                organization_id=organization_id,
                status="failed",
                claim_token=notification_token,
                failure_reason=failure_type,
            )
        )
        return "notification_failed"
    runtime.run(
        lambda factory: mark_curation_notification(
            factory,
            job_id=job_id,
            organization_id=organization_id,
            status="sent",
            claim_token=notification_token,
        )
    )
    logger.info(
        "adoption_curation_completed",
        extra={
            "job_id": str(job_id),
            "organization_id": str(organization_id),
            "draft_id": str(draft_id),
            "expected_version": expected_version,
            "actual_version": notification.actual_version,
            "job_type": "adoption_recommendation_curation",
            "notification_status": "sent",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return "succeeded"


async def _push_curation_result(
    *,
    organization_id: UUID,
    job_id: UUID,
    notification: CurationNotification,
) -> None:
    if notification.candidates:
        cards = [
            _curation_card(organization_id, candidate, rank=index)
            for index, candidate in enumerate(notification.candidates, start=1)
        ]
        messages = [
            {"type": "text", "text": f"🤖 AI 幫你精選了 {len(cards)} 隻適合的毛孩："},
            build_match_report(cards, max_bubbles=5),
        ]
    else:
        messages = [{"type": "text", "text": "目前沒有仍可領養的符合候選，請瀏覽其他毛孩。"}]
    async with httpx.AsyncClient(timeout=10) as client:
        await LineMessagingApiAdapter(client=client).push(
            to_user_id=notification.line_user_id,
            messages=messages,
            retry_key=str(uuid5(NAMESPACE_URL, f"strayhub:{job_id}:adoption-curation")),
        )


def _curation_card(
    organization_id: UUID, candidate: CuratedCandidate, *, rank: int
) -> MatchReportCard:
    photo_url = None
    base_url = get_worker_settings().web_public_base_url.strip().rstrip("/")
    if base_url.startswith("https://") and candidate.current_photo_key:
        token = issue_adoption_photo_token(
            organization_id=organization_id,
            animal_id=candidate.animal_id,
            object_key=candidate.current_photo_key,
            ttl_seconds=300,
        )
        photo_url = (
            f"{base_url}/v1/public/adoption/animals/{candidate.animal_id}/photo?token={token}"
        )
    return MatchReportCard(
        animal_id=str(candidate.animal_id),
        name=candidate.name,
        shelter_number=candidate.shelter_number,
        photo_url=photo_url,
        score=int(candidate.score) if candidate.score is not None else None,
        reasons=candidate.reasons,
        rank=rank,
        selectable=True,
    )


@celery_app.task(bind=True, name="adoption.generate_followups")
def generate_followups(
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
    started = time.monotonic()
    snapshot = runtime.run(
        lambda factory: claim_followup_job(
            factory,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            worker_name=str(self.request.hostname or "celery-worker"),
        )
    )
    if snapshot is None:
        return _deliver_followup_notification(
            self,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            started=started,
        )
    settings = get_worker_settings()
    recommendations = []
    failure_reason = snapshot.skip_ai_reason
    gemini = None
    try:
        if snapshot.skip_ai_reason is None and (
            settings.gemini_service_account_path or settings.gemini_api_key
        ):
            gemini = GeminiClient(
                model_name=settings.gemini_model_name,
                api_key=settings.gemini_api_key,
                service_account_path=settings.gemini_service_account_path,
                location=settings.gemini_vertex_location,
                timeout_seconds=max(
                    0.25,
                    min(20.0, float(settings.celery_task_soft_time_limit - 1)),
                ),
            )
            recommendations = runtime.run(
                lambda _factory: gemini.recommend_alternatives_strict(
                    snapshot.prompt,
                    valid_animal_ids={str(item) for item in snapshot.candidate_ids},
                )
            )
        elif snapshot.skip_ai_reason is None:
            failure_reason = "gemini_unconfigured"
    except (TransientAiError, SoftTimeLimitExceeded) as exc:
        if snapshot.retry_count < settings.celery_max_retries:
            countdown = _countdown(snapshot.retry_count, settings.celery_retry_backoff_max)
            failure_type = type(exc).__name__
            runtime.run(
                lambda factory: mark_followup_retry(
                    factory,
                    job_id=job_uuid,
                    organization_id=organization_uuid,
                    claim_token=claim_token,
                    failure_reason=failure_type,
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
        lambda factory: apply_followup_result(
            factory,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            recommendations=recommendations,
            failure_reason=failure_reason,
        )
    )
    if not outcome.applied:
        logger.info(
            "adoption_followup_not_applied",
            extra={
                "job_id": job_id,
                "organization_id": organization_id,
                "draft_id": resource_id,
                "expected_version": expected_version,
                "actual_version": outcome.actual_version,
                "job_type": "adoption_followup_recommendations",
                "stale_discard": outcome.stale,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return "stale" if outcome.stale else "duplicate"
    return _deliver_followup_notification(
        self,
        job_id=job_uuid,
        draft_id=draft_uuid,
        organization_id=organization_uuid,
        expected_version=expected_version,
        started=started,
    )


def _deliver_followup_notification(
    task: Task,
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    started: float,
) -> str:
    settings = get_worker_settings()
    notification_token = str(uuid4())
    notification = runtime.run(
        lambda factory: claim_followup_notification(
            factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=expected_version,
            claim_token=notification_token,
        )
    )
    if notification is None:
        return "discarded_or_duplicate"
    try:
        runtime.run(
            lambda _factory: _push_followup_result(
                organization_id=organization_id,
                job_id=job_id,
                notification=notification,
            )
        )
    except Exception as exc:
        failure_type = type(exc).__name__
        if task.request.retries < settings.celery_max_retries:
            countdown = _countdown(task.request.retries, settings.celery_retry_backoff_max)
            runtime.run(
                lambda factory: mark_followup_notification(
                    factory,
                    job_id=job_id,
                    organization_id=organization_id,
                    status="retry_wait",
                    claim_token=notification_token,
                    failure_reason=failure_type,
                    countdown=countdown,
                )
            )
            raise task.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.celery_max_retries,
            ) from exc
        runtime.run(
            lambda factory: mark_followup_notification(
                factory,
                job_id=job_id,
                organization_id=organization_id,
                status="failed",
                claim_token=notification_token,
                failure_reason=failure_type,
            )
        )
        return "notification_failed"
    runtime.run(
        lambda factory: mark_followup_notification(
            factory,
            job_id=job_id,
            organization_id=organization_id,
            status="sent",
            claim_token=notification_token,
        )
    )
    logger.info(
        "adoption_followup_completed",
        extra={
            "job_id": str(job_id),
            "organization_id": str(organization_id),
            "draft_id": str(draft_id),
            "expected_version": expected_version,
            "actual_version": notification.actual_version,
            "job_type": "adoption_followup_recommendations",
            "notification_status": "sent",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return "succeeded"


async def _push_followup_result(
    *,
    organization_id: UUID,
    job_id: UUID,
    notification: FollowupNotification,
) -> None:
    messages: list[dict]
    if notification.state == AdoptionDraftState.AWAITING_ADOPTER_NAME:
        messages = [
            {"type": "text", "text": "這次沒有找到可用的替代建議，不過申請仍可繼續 🐾"},
            build_info_card("請留下您的姓名 🧑‍🤝‍🧑", accent_index=1, body="請直接輸入姓名"),
        ]
    else:
        cards: list[MatchReportCard] = []
        if notification.original is not None:
            cards.append(
                _followup_card(
                    organization_id,
                    notification.original,
                    reason="你原本選定的毛孩",
                    label="維持這隻",
                )
            )
        cards.extend(
            _followup_card(organization_id, candidate, reason=reason, label="換成這隻")
            for candidate, reason in notification.alternatives
        )
        intro = (
            "這幾隻毛孩你可以參考看看，也可以維持原本的選擇："
            if notification.alternatives
            else "這次沒有找到其他更適合的建議，你原本選擇的毛孩依然值得考慮 🐾"
        )
        messages = [{"type": "text", "text": intro}, build_match_report(cards, max_bubbles=5)]
    async with httpx.AsyncClient(timeout=10) as client:
        await LineMessagingApiAdapter(client=client).push(
            to_user_id=notification.line_user_id,
            messages=messages,
            retry_key=str(uuid5(NAMESPACE_URL, f"strayhub:{job_id}:adoption-followup")),
        )


def _followup_card(
    organization_id: UUID,
    candidate: FollowupCandidate,
    *,
    reason: str,
    label: str,
) -> MatchReportCard:
    photo_url = None
    base_url = get_worker_settings().web_public_base_url.strip().rstrip("/")
    if base_url.startswith("https://") and candidate.current_photo_key:
        token = issue_adoption_photo_token(
            organization_id=organization_id,
            animal_id=candidate.animal_id,
            object_key=candidate.current_photo_key,
            ttl_seconds=300,
        )
        photo_url = (
            f"{base_url}/v1/public/adoption/animals/{candidate.animal_id}/photo?token={token}"
        )
    return MatchReportCard(
        animal_id=str(candidate.animal_id),
        name=candidate.name,
        shelter_number=candidate.shelter_number,
        photo_url=photo_url,
        reasons=(reason,),
        selectable=True,
        select_action="select_alternative_animal",
        select_label=label,
    )


@celery_app.task(bind=True, name="adoption.extract_profile")
def extract_profile(
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
    started = time.monotonic()
    snapshot = runtime.run(
        lambda factory: claim_profile_extraction_job(
            factory,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            worker_name=str(self.request.hostname or "celery-worker"),
        )
    )
    if snapshot is None:
        return _deliver_profile_notification(
            self,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            started=started,
        )
    settings = get_worker_settings()
    extracted: dict[str, str] = {}
    failure_reason: str | None = snapshot.skip_ai_reason
    gemini = None
    try:
        if snapshot.skip_ai_reason is None and (
            settings.gemini_service_account_path or settings.gemini_api_key
        ):
            gemini = GeminiClient(
                model_name=settings.gemini_model_name,
                api_key=settings.gemini_api_key,
                service_account_path=settings.gemini_service_account_path,
                location=settings.gemini_vertex_location,
                timeout_seconds=max(
                    0.25,
                    min(20.0, float(settings.celery_task_soft_time_limit - 1)),
                ),
            )
            extracted = runtime.run(
                lambda _factory: gemini.extract_adoption_profile_strict(
                    snapshot.prompt,
                    valid_values=snapshot.valid_values,
                )
            )
        elif snapshot.skip_ai_reason is None:
            failure_reason = "gemini_unconfigured"
    except (TransientAiError, SoftTimeLimitExceeded) as exc:
        if snapshot.retry_count < settings.celery_max_retries:
            countdown = _countdown(snapshot.retry_count, settings.celery_retry_backoff_max)
            failure_type = type(exc).__name__
            runtime.run(
                lambda factory: mark_profile_extraction_retry(
                    factory,
                    job_id=job_uuid,
                    organization_id=organization_uuid,
                    claim_token=claim_token,
                    failure_reason=failure_type,
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
        lambda factory: apply_profile_extraction_result(
            factory,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            extracted=extracted,
            failure_reason=failure_reason,
        )
    )
    if not outcome.applied:
        logger.info(
            "adoption_profile_extraction_not_applied",
            extra={
                "job_id": job_id,
                "celery_task_id": claim_token,
                "organization_id": organization_id,
                "draft_id": resource_id,
                "expected_version": expected_version,
                "actual_version": outcome.actual_version,
                "job_type": "adoption_profile_extraction",
                "attempt": snapshot.retry_count + 1,
                "retry_reason": failure_reason,
                "stale_discard": outcome.stale,
                "notification_status": "not_started",
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return "stale" if outcome.stale else "duplicate"
    if outcome.next_job_id is not None:
        runtime.run(lambda _factory: dispatch_ai_job(outcome.next_job_id, organization_uuid))
    return _deliver_profile_notification(
        self,
        job_id=job_uuid,
        draft_id=draft_uuid,
        organization_id=organization_uuid,
        expected_version=expected_version,
        started=started,
    )


def _deliver_profile_notification(
    task: Task,
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    started: float,
) -> str:
    settings = get_worker_settings()
    notification_claim_token = str(uuid4())
    notification = runtime.run(
        lambda factory: claim_profile_extraction_notification(
            factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=expected_version,
            claim_token=notification_claim_token,
        )
    )
    if notification is None:
        return "discarded_or_duplicate"
    try:
        runtime.run(
            lambda _factory: _push_profile_extraction_result(
                organization_id=organization_id,
                job_id=job_id,
                notification=notification,
            )
        )
    except Exception as exc:
        failure_type = type(exc).__name__
        if task.request.retries < settings.celery_max_retries:
            countdown = _countdown(task.request.retries, settings.celery_retry_backoff_max)
            runtime.run(
                lambda factory: mark_profile_extraction_notification(
                    factory,
                    job_id=job_id,
                    organization_id=organization_id,
                    status="retry_wait",
                    claim_token=notification_claim_token,
                    failure_reason=failure_type,
                    countdown=countdown,
                )
            )
            raise task.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.celery_max_retries,
            ) from exc
        runtime.run(
            lambda factory: mark_profile_extraction_notification(
                factory,
                job_id=job_id,
                organization_id=organization_id,
                status="failed",
                claim_token=notification_claim_token,
                failure_reason=failure_type,
            )
        )
        return "notification_failed"
    runtime.run(
        lambda factory: mark_profile_extraction_notification(
            factory,
            job_id=job_id,
            organization_id=organization_id,
            status="sent",
            claim_token=notification_claim_token,
        )
    )
    logger.info(
        "adoption_profile_extraction_completed",
        extra={
            "job_id": str(job_id),
            "celery_task_id": str(task.request.id or job_id),
            "organization_id": str(organization_id),
            "draft_id": str(draft_id),
            "expected_version": expected_version,
            "actual_version": notification.actual_version,
            "job_type": "adoption_profile_extraction",
            "attempt": task.request.retries + 1,
            "stale_discard": False,
            "notification_status": "sent",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return "succeeded"


async def _push_profile_extraction_result(
    *,
    organization_id: UUID,
    job_id: UUID,
    notification: ProfileExtractionNotification,
) -> None:
    include_recommend_me_keys = notification.path == "recommend_me"
    summary = build_info_card(
        "AI 已整理問卷內容 🤖",
        accent_index=1,
        body="已填入你明確提到的項目；未提到的內容仍會由系統詢問。",
        rows=build_profile_summary_rows(
            include_recommend_me_keys=include_recommend_me_keys,
            answers=notification.answers,
        ),
    )
    if notification.state == AdoptionDraftState.AWAITING_FREETEXT_PROFILE:
        guidance = "還可以再補充一次生活狀況，或點選「改為逐題回答」。"
    elif notification.state == AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS:
        guidance = "問卷已整理完成，正在準備推薦名單。"
    else:
        guidance = "問卷已整理完成，請重新點選「領養媒合」繼續目前題目。"
    async with httpx.AsyncClient(timeout=10) as client:
        line = LineMessagingApiAdapter(client=client)
        await line.push(
            to_user_id=notification.line_user_id,
            messages=[summary, {"type": "text", "text": guidance}],
            retry_key=str(uuid5(NAMESPACE_URL, f"strayhub:{job_id}:profile-extraction")),
        )


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
    started = time.monotonic()
    logger.info(
        "adoption_suitability_started",
        extra={
            "job_id": job_id,
            "celery_task_id": claim_token,
            "organization_id": organization_id,
            "draft_id": resource_id,
            "expected_version": expected_version,
            "job_type": "adoption_suitability",
            "attempt": self.request.retries + 1,
        },
    )
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
        return _deliver_notification(
            self,
            job_id=job_uuid,
            draft_id=draft_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            started=started,
        )

    settings = get_worker_settings()
    result = None
    failure_reason = None
    gemini = None
    try:
        if snapshot.skip_ai_reason:
            failure_reason = snapshot.skip_ai_reason
        elif settings.gemini_service_account_path or settings.gemini_api_key:
            gemini = GeminiClient(
                model_name=settings.gemini_model_name,
                api_key=settings.gemini_api_key,
                service_account_path=settings.gemini_service_account_path,
                location=settings.gemini_vertex_location,
                timeout_seconds=max(
                    0.25,
                    min(20.0, float(settings.celery_task_soft_time_limit - 1)),
                ),
            )
            result = runtime.run(
                lambda _factory: gemini.analyze_suitability_strict(snapshot.prompt)
            )
        else:
            failure_reason = "gemini_unconfigured"
    except (TransientAiError, SoftTimeLimitExceeded) as exc:
        if snapshot.retry_count < settings.celery_max_retries:
            countdown = _countdown(snapshot.retry_count, settings.celery_retry_backoff_max)
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
            logger.warning(
                "adoption_suitability_retry",
                extra={
                    "job_id": job_id,
                    "celery_task_id": claim_token,
                    "organization_id": organization_id,
                    "draft_id": resource_id,
                    "expected_version": expected_version,
                    "job_type": "adoption_suitability",
                    "attempt": self.request.retries + 1,
                    "retry_reason": type(exc).__name__,
                    "stale_discard": False,
                    "notification_status": "not_started",
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                },
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
        logger.info(
            "adoption_suitability_result_not_applied",
            extra={
                "job_id": job_id,
                "celery_task_id": claim_token,
                "organization_id": organization_id,
                "draft_id": resource_id,
                "expected_version": expected_version,
                "actual_version": outcome.actual_version,
                "job_type": "adoption_suitability",
                "attempt": self.request.retries + 1,
                "retry_reason": failure_reason,
                "stale_discard": outcome.stale,
                "notification_status": "not_started",
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return "stale" if outcome.stale else "duplicate"
    return _deliver_notification(
        self,
        job_id=job_uuid,
        draft_id=draft_uuid,
        organization_id=organization_uuid,
        expected_version=expected_version,
        started=started,
    )


def _deliver_notification(
    task: Task,
    *,
    job_id: UUID,
    draft_id: UUID,
    organization_id: UUID,
    expected_version: int,
    started: float,
) -> str:
    settings = get_worker_settings()
    notification_claim_token = str(uuid4())
    notification = runtime.run(
        lambda factory: claim_suitability_notification(
            factory,
            job_id=job_id,
            draft_id=draft_id,
            organization_id=organization_id,
            expected_version=expected_version,
            claim_token=notification_claim_token,
        )
    )
    if notification is None:
        return "discarded_or_duplicate"
    try:
        runtime.run(
            lambda _factory: _push_suitability_result(
                organization_id=organization_id,
                job_id=job_id,
                notification=notification,
            )
        )
    except Exception as exc:
        failure_type = type(exc).__name__
        if task.request.retries < settings.celery_max_retries:
            countdown = _countdown(task.request.retries, settings.celery_retry_backoff_max)
            runtime.run(
                lambda factory: mark_suitability_notification(
                    factory,
                    job_id=job_id,
                    organization_id=organization_id,
                    status="retry_wait",
                    failure_reason=failure_type,
                    claim_token=notification_claim_token,
                    countdown=countdown,
                )
            )
            logger.warning(
                "adoption_suitability_notification_retry",
                extra={
                    "job_id": str(job_id),
                    "celery_task_id": str(task.request.id or job_id),
                    "organization_id": str(organization_id),
                    "draft_id": str(draft_id),
                    "expected_version": expected_version,
                    "actual_version": notification.outcome.actual_version,
                    "job_type": "adoption_suitability",
                    "retry_reason": failure_type,
                    "attempt": task.request.retries + 1,
                    "stale_discard": False,
                    "notification_status": "retry_wait",
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                },
            )
            raise task.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.celery_max_retries,
            ) from exc
        runtime.run(
            lambda factory: mark_suitability_notification(
                factory,
                job_id=job_id,
                organization_id=organization_id,
                status="failed",
                failure_reason=failure_type,
                claim_token=notification_claim_token,
            )
        )
        logger.exception(
            "adoption_suitability_notification_failed",
            extra={
                "job_id": str(job_id),
                "celery_task_id": str(task.request.id or job_id),
                "organization_id": str(organization_id),
                "draft_id": str(draft_id),
                "expected_version": expected_version,
                "actual_version": notification.outcome.actual_version,
                "job_type": "adoption_suitability",
                "retry_reason": failure_type,
                "attempt": task.request.retries + 1,
                "stale_discard": False,
                "notification_status": "failed",
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return "notification_failed"
    runtime.run(
        lambda factory: mark_suitability_notification(
            factory,
            job_id=job_id,
            organization_id=organization_id,
            status="sent",
            claim_token=notification_claim_token,
        )
    )
    logger.info(
        "adoption_suitability_completed",
        extra={
            "job_id": str(job_id),
            "celery_task_id": str(task.request.id or job_id),
            "organization_id": str(organization_id),
            "draft_id": str(draft_id),
            "expected_version": expected_version,
            "actual_version": notification.outcome.actual_version,
            "job_type": "adoption_suitability",
            "attempt": task.request.retries + 1,
            "retry_reason": None,
            "stale_discard": False,
            "notification_status": "sent",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return "succeeded"


async def _push_suitability_result(
    *,
    organization_id: UUID,
    job_id: UUID,
    notification: SuitabilityNotification,
) -> None:
    outcome: SuitabilityOutcome = notification.outcome
    if outcome.snapshot is None:
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
            to_user_id=notification.line_user_id,
            messages=messages,
            retry_key=str(uuid5(NAMESPACE_URL, f"strayhub:{job_id}:adopter-suitability")),
        )
