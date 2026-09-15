from __future__ import annotations

import time
from functools import partial
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from billiard.exceptions import SoftTimeLimitExceeded
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from celery import Task

from services.api.app.application.growth_diary_ai_analysis_service import (
    GrowthDiaryAiAnalysisService,
)
from services.api.app.application.growth_diary_job_service import (
    GrowthDiaryDelivery,
    apply_growth_diary_result,
    claim_growth_diary_job,
    claim_growth_diary_notifications,
    mark_growth_diary_delivery,
    mark_growth_diary_retry,
)
from services.api.app.application.line_growth_diary_flex import (
    build_growth_diary_ai_reply_card,
    growth_diary_quick_reply_items,
)
from services.api.app.config.settings import get_worker_settings
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiClient,
    PermanentAiError,
    TransientAiError,
)
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope
from services.api.app.observability.logging import get_logger
from services.worker.app.celery_runtime import runtime

logger = get_logger(__name__)


class TransientStorageError(RuntimeError):
    pass


class PermanentStorageError(RuntimeError):
    pass


def _countdown(retries: int, maximum: int) -> int:
    return min(5 * (2**retries), maximum)


async def fetch_growth_diary_photo(*, organization_id: UUID, key: str) -> tuple[bytes, str]:
    try:
        data, content_type = await MinioStorageAdapter().get_with_content_type(
            scope=ObjectScope(organization_id), key=key
        )
    except (
        EndpointConnectionError,
        ConnectionClosedError,
        ConnectTimeoutError,
        ReadTimeoutError,
        TimeoutError,
        ConnectionError,
    ) as exc:
        raise TransientStorageError(type(exc).__name__) from exc
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = str(error.get("Code", ""))
        status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
        if status >= 500 or code in {
            "InternalError",
            "RequestTimeout",
            "ServiceUnavailable",
            "SlowDown",
        }:
            raise TransientStorageError(code or f"storage_http_{status}") from exc
        raise PermanentStorageError(code or f"storage_http_{status}") from exc
    if not data or content_type != "image/webp":
        raise PermanentStorageError("invalid_growth_diary_media")
    return data, content_type


@celery_app.task(bind=True, name="growth_diary.analyze_entry")
def analyze_entry(
    self: Task,
    *,
    job_id: str,
    resource_id: str,
    organization_id: str,
    expected_version: int,
) -> str:
    job_uuid = UUID(job_id)
    entry_uuid = UUID(resource_id)
    organization_uuid = UUID(organization_id)
    claim_token = str(self.request.id or job_uuid)
    started = time.monotonic()
    snapshot = runtime.run(
        lambda factory: claim_growth_diary_job(
            factory,
            job_id=job_uuid,
            entry_id=entry_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            worker_name=str(self.request.hostname or "celery-worker"),
        )
    )
    if snapshot is None:
        return _deliver_notifications(
            self,
            job_id=job_uuid,
            entry_id=entry_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            started=started,
        )
    settings = get_worker_settings()
    photo: bytes | None = None
    photo_mime_type: str | None = None
    failure_reason = snapshot.skip_ai_reason
    result = None
    gemini = None
    try:
        if snapshot.photo_key and snapshot.skip_ai_reason is None:
            try:
                photo, photo_mime_type = runtime.run(
                    lambda _factory: fetch_growth_diary_photo(
                        organization_id=organization_uuid, key=snapshot.photo_key or ""
                    )
                )
            except TransientStorageError as exc:
                if snapshot.retry_count < settings.celery_max_retries:
                    _retry_analysis(
                        self,
                        job_id=job_uuid,
                        organization_id=organization_uuid,
                        claim_token=claim_token,
                        retry_count=snapshot.retry_count,
                        reason=type(exc).__name__,
                    )
                failure_reason = f"storage_retry_exhausted:{type(exc).__name__}"
            except PermanentStorageError as exc:
                failure_reason = f"storage_permanent:{exc}"
        can_analyze = bool(snapshot.note or photo is not None)
        if snapshot.skip_ai_reason is None and can_analyze and (settings.gemini_configured):
            gemini = GeminiClient(
                model_name=settings.gemini_model_name,
                api_key=settings.gemini_api_key,
                service_account_path=settings.gemini_service_account_path,
                location=settings.gemini_vertex_location,
                use_runtime_identity=settings.gemini_use_runtime_identity,
                project_id=settings.gemini_vertex_project,
                runtime_service_account=settings.gemini_runtime_service_account,
                timeout_seconds=max(
                    0.25,
                    min(20.0, float(settings.celery_task_soft_time_limit - 1)),
                ),
            )
            result = runtime.run(
                lambda _factory: GrowthDiaryAiAnalysisService(gemini).analyze_entry_strict(
                    animal_name=snapshot.animal_name,
                    note=snapshot.note,
                    photo=photo,
                    photo_mime_type=photo_mime_type,
                )
            )
        elif snapshot.skip_ai_reason is None and can_analyze:
            failure_reason = "gemini_unconfigured"
        elif not can_analyze:
            failure_reason = failure_reason or "photo_unavailable_without_text"
    except (TransientAiError, SoftTimeLimitExceeded) as exc:
        if snapshot.retry_count < settings.celery_max_retries:
            _retry_analysis(
                self,
                job_id=job_uuid,
                organization_id=organization_uuid,
                claim_token=claim_token,
                retry_count=snapshot.retry_count,
                reason=type(exc).__name__,
            )
        failure_reason = f"retry_exhausted:{type(exc).__name__}"
    except PermanentAiError as exc:
        failure_reason = f"permanent:{type(exc).__name__}"
    finally:
        if gemini is not None:
            runtime.run(lambda _factory: gemini.aclose())
    outcome = runtime.run(
        lambda factory: apply_growth_diary_result(
            factory,
            job_id=job_uuid,
            entry_id=entry_uuid,
            organization_id=organization_uuid,
            expected_version=expected_version,
            claim_token=claim_token,
            result=result,
            failure_reason=failure_reason,
        )
    )
    if not outcome.applied:
        return "stale" if outcome.stale else "duplicate"
    return _deliver_notifications(
        self,
        job_id=job_uuid,
        entry_id=entry_uuid,
        organization_id=organization_uuid,
        expected_version=expected_version,
        started=started,
    )


def _retry_analysis(
    task: Task,
    *,
    job_id: UUID,
    organization_id: UUID,
    claim_token: str,
    retry_count: int,
    reason: str,
) -> None:
    settings = get_worker_settings()
    countdown = _countdown(retry_count, settings.celery_retry_backoff_max)
    runtime.run(
        lambda factory: mark_growth_diary_retry(
            factory,
            job_id=job_id,
            organization_id=organization_id,
            claim_token=claim_token,
            failure_reason=reason,
            countdown=countdown,
        )
    )
    raise task.retry(
        exc=TransientAiError(reason),
        countdown=countdown,
        max_retries=settings.celery_max_retries,
    )


def _deliver_notifications(
    task: Task,
    *,
    job_id: UUID,
    entry_id: UUID,
    organization_id: UUID,
    expected_version: int,
    started: float,
) -> str:
    claim_token = str(uuid4())
    deliveries = runtime.run(
        lambda factory: claim_growth_diary_notifications(
            factory,
            job_id=job_id,
            entry_id=entry_id,
            organization_id=organization_id,
            expected_version=expected_version,
            claim_token=claim_token,
        )
    )
    if not deliveries:
        return "discarded_or_duplicate"
    settings = get_worker_settings()
    failures: list[Exception] = []
    for delivery in deliveries:
        try:
            runtime.run(
                lambda _factory, delivery=delivery: _push_delivery(
                    organization_id=organization_id,
                    job_id=job_id,
                    delivery=delivery,
                )
            )
        except Exception as exc:
            failures.append(exc)
            retrying = task.request.retries < settings.celery_max_retries
            countdown = (
                _countdown(task.request.retries, settings.celery_retry_backoff_max)
                if retrying
                else None
            )
            runtime.run(
                partial(
                    mark_growth_diary_delivery,
                    job_id=job_id,
                    organization_id=organization_id,
                    delivery_id=delivery.delivery_id,
                    claim_token=claim_token,
                    status="retry_wait" if retrying else "exhausted",
                    failure_reason=type(exc).__name__,
                    countdown=countdown,
                )
            )
        else:
            runtime.run(
                lambda factory, delivery=delivery: mark_growth_diary_delivery(
                    factory,
                    job_id=job_id,
                    organization_id=organization_id,
                    delivery_id=delivery.delivery_id,
                    claim_token=claim_token,
                    status="sent",
                )
            )
    if failures and task.request.retries < settings.celery_max_retries:
        countdown = _countdown(task.request.retries, settings.celery_retry_backoff_max)
        raise task.retry(
            exc=failures[0],
            countdown=countdown,
            max_retries=settings.celery_max_retries,
        )
    logger.info(
        "growth_diary_analysis_completed",
        extra={
            "job_id": str(job_id),
            "organization_id": str(organization_id),
            "entry_id": str(entry_id),
            "expected_version": expected_version,
            "notification_count": len(deliveries),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return "notification_failed" if failures else "succeeded"


async def _push_delivery(
    *,
    organization_id: UUID,
    job_id: UUID,
    delivery: GrowthDiaryDelivery,
) -> None:
    message: dict
    if delivery.purpose == "staff":
        message = {
            "type": "text",
            "text": (
                "⚠️ 毛孩日記異常通知\n"
                f"{delivery.animal_name} 的領養者剛回報疑似健康狀況異常：\n"
                f"「{delivery.staff_summary}」\n"
                "請儘快確認並視需要主動聯繫領養者。"
            ),
        }
    elif delivery.adopter_reply:
        message = build_growth_diary_ai_reply_card(
            mood=delivery.mood or "neutral", reply_text=delivery.adopter_reply
        )
    else:
        message = {
            "type": "text",
            "text": "已收到這篇近況紀錄。",
            "quickReply": {"items": growth_diary_quick_reply_items(include_back_to_default=True)},
        }
    async with httpx.AsyncClient(timeout=10) as client:
        await LineMessagingApiAdapter(client=client, settings=get_worker_settings()).push(
            to_user_id=delivery.line_user_id,
            messages=[message],
            retry_key=str(
                uuid5(
                    NAMESPACE_URL,
                    f"strayhub:{job_id}:growth-diary:{delivery.purpose}:{delivery.user_id}",
                )
            ),
        )
