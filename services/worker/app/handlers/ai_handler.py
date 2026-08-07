from __future__ import annotations

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
    ) -> object:
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
                observation.status = "ready_for_review"
            job.status = "succeeded"
        except Exception as error:
            # Preserve a safe error code, not provider response or source content.
            if getattr(job, "raw_ai_output", None) is None:
                job.raw_ai_output = None
            job.validation_result = {"status": "invalid"}
            job.failure_reason = type(error).__name__
            job.status = "failed"
            job.retry_count = getattr(job, "retry_count", 0) + 1
            if observation is not None:
                observation.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
        return job

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
