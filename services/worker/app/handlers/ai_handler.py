from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from services.api.app.api.errors import DomainError
from services.worker.app.handlers.ai_validation import validate_ai_output
from services.worker.app.infrastructure.ai_port import AIClientPort, AIRequestVersion


class AIJobHandler:
    def __init__(self, client: AIClientPort) -> None:
        self.client = client

    async def handle(
        self,
        job: object,
        *,
        note: str | None,
        cleaned_images: list[bytes],
        allowed_codes: set[str],
        observation: object | None = None,
        organization_id: object | None = None,
        report: object | None = None,
        media_assets: list[object] | None = None,
        source_type: str | None = None,
        source_id: object | None = None,
    ) -> object:
        if getattr(job, "status", None) in {"succeeded", "invalid"}:
            return job
        self._validate_context(
            job,
            organization_id=organization_id,
            report=report,
            media_assets=media_assets or [],
        )
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        version = AIRequestVersion(
            provider=job.provider,
            model_name=job.model_name,
            model_version=job.model_version,
            prompt_version=job.prompt_version,
            output_schema_version=job.output_schema_version,
            prompt_template_id=getattr(job, "prompt_template_id", "care-observation"),
        )
        self._set_source_trace(
            observation,
            source_type=source_type,
            source_id=source_id,
            note=note,
            report=report,
            media_assets=media_assets or [],
        )
        try:
            output = await self.client.analyze(
                note=note,
                image_bytes=cleaned_images,
                version=version,
            )
            job.raw_ai_output = output
            validated = validate_ai_output(output, allowed_codes=allowed_codes)
            job.validation_result = {"status": "valid"}
            if observation is not None:
                observation.raw_ai_output = output
                observation.validated_ai_observation = validated
                observation.status = "succeeded"
            job.status = "succeeded"
            if report is not None and hasattr(report, "ai_job_status"):
                report.ai_job_status = "succeeded"
        except DomainError as error:
            # Validation failures retain the provider payload for authorized review,
            # but never promote it to a formal observation.
            if getattr(job, "raw_ai_output", None) is None:
                job.raw_ai_output = output if "output" in locals() else None
            job.validation_result = {"status": "invalid", "error_code": error.code}
            job.failure_reason = error.code
            job.status = "invalid"
            job.retry_count = (getattr(job, "retry_count", 0) or 0) + 1
            if observation is not None:
                observation.raw_ai_output = job.raw_ai_output
                observation.validated_ai_observation = None
                observation.status = "invalid"
            if report is not None and hasattr(report, "ai_job_status"):
                report.ai_job_status = "invalid"
        except asyncio.CancelledError:
            self._mark_failure(job, observation, report, "ai_interrupted")
        except Exception as error:
            # Preserve a safe error code, not provider response or source content.
            failure_reason = getattr(error, "code", None) or {
                TimeoutError: "TimeoutError",
                ConnectionError: "ConnectionError",
            }.get(type(error), "ai_provider_error")
            self._mark_failure(job, observation, report, failure_reason)
        job.completed_at = datetime.now(timezone.utc)
        return job

    @staticmethod
    def _mark_failure(job, observation, report, failure_reason: str) -> None:
        job.raw_ai_output = getattr(job, "raw_ai_output", None)
        job.validation_result = {"status": "failed", "error_code": failure_reason}
        job.failure_reason = failure_reason
        job.status = "failed"
        job.retry_count = (getattr(job, "retry_count", 0) or 0) + 1
        if observation is not None:
            observation.status = "failed"
        if report is not None and hasattr(report, "ai_job_status"):
            report.ai_job_status = "failed"

    @staticmethod
    def _set_source_trace(
        observation,
        *,
        source_type: str | None,
        source_id: object | None,
        note: str | None,
        report: object | None,
        media_assets: list[object],
    ) -> None:
        if observation is None:
            return
        if source_type is not None:
            observation.source_type = source_type
            observation.source_id = source_id
            return
        current_source = getattr(observation, "source_type", None)
        if current_source == "photo" and getattr(observation, "source_id", None) is None:
            if media_assets and getattr(media_assets[0], "id", None) is not None:
                observation.source_id = media_assets[0].id
            return
        if current_source == "note" and getattr(observation, "source_id", None) is None:
            if report is not None and getattr(report, "id", None) is not None:
                observation.source_id = report.id
            return
        if current_source in {"note", "photo"}:
            return
        if current_source == "care_report" and note and report is not None:
            observation.source_type = "note"
            observation.source_id = report.id
            return
        if media_assets and getattr(media_assets[0], "id", None) is not None:
            observation.source_type = "photo"
            observation.source_id = media_assets[0].id
        elif note and report is not None and getattr(report, "id", None) is not None:
            observation.source_type = "note"
            observation.source_id = report.id

    @staticmethod
    def _validate_context(
        job: object,
        *,
        organization_id: object | None,
        report: object | None,
        media_assets: list[object],
    ) -> None:
        job_org = getattr(job, "organization_id", None)
        if organization_id is not None and job_org != organization_id:
            raise DomainError("cross_tenant_job", "AI Job 與目前收容所不一致", 404)
        if report is not None:
            if getattr(report, "organization_id", None) != job_org:
                raise DomainError("cross_tenant_job", "AI Report 與 Job 不一致", 404)
            if getattr(job, "target_type", "care_report") == "care_report" and getattr(
                job, "target_id", getattr(report, "id", None)
            ) != getattr(report, "id", None):
                raise DomainError("job_target_mismatch", "AI Job 目標回報不一致", 409)
        for media in media_assets:
            if getattr(media, "organization_id", None) != job_org:
                raise DomainError("cross_tenant_media", "AI 媒體與 Job 不一致", 404)
            if not getattr(media, "exif_removed", False):
                raise DomainError("unsafe_media", "AI 只能讀取已清理圖片", 422)
            if getattr(media, "status", "processed") not in {"processed", "attached"}:
                raise DomainError("media_not_ready", "圖片尚未完成清理", 409)
