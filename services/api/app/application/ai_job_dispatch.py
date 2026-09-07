from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from services.api.app.config.settings import get_settings
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.repositories.ai_job_repository import AIJobRepository


@dataclass(frozen=True)
class AIJobVersion:
    provider: str
    model_name: str
    model_version: str
    prompt_template_id: str
    prompt_version: str
    output_schema_version: str


def configured_ai_version() -> AIJobVersion:
    settings = get_settings()
    stool_configured = bool(settings.stool_api_url and settings.stool_api_key)
    return AIJobVersion(
        provider="stool-analysis" if stool_configured else settings.ai_provider,
        model_name=settings.ai_model_name,
        model_version=settings.ai_model_version,
        prompt_template_id=settings.ai_prompt_template_id,
        prompt_version=settings.ai_prompt_version,
        output_schema_version=settings.ai_output_schema_version,
    )


async def create_ai_job(
    repository: AIJobRepository,
    *,
    target_type: str,
    target_id: UUID,
    job_type: str = "care_observation",
) -> AIProcessingJob:
    version = configured_ai_version()
    if job_type == "care_report_summary":
        settings = get_settings()
        version = AIJobVersion(
            provider="gemini",
            model_name=settings.gemini_model_name,
            model_version=settings.gemini_model_name,
            prompt_template_id="care-report-summary",
            prompt_version="2",
            output_schema_version="1",
        )
    return await repository.create(
        AIProcessingJob(
            organization_id=repository.organization_id,
            job_type=job_type,
            target_type=target_type,
            target_id=target_id,
            domain_version=0,
            execution_backend="legacy_polling",
            provider=version.provider,
            model_name=version.model_name,
            model_version=version.model_version,
            prompt_template_id=version.prompt_template_id,
            prompt_version=version.prompt_version,
            output_schema_version=version.output_schema_version,
            status="pending_enqueue",
            retry_count=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )


async def create_adoption_suitability_job(
    repository: AIJobRepository,
    *,
    draft_id: UUID,
    domain_version: int,
) -> AIProcessingJob:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return await repository.create(
        AIProcessingJob(
            organization_id=repository.organization_id,
            job_type="adoption_suitability",
            target_type="adoption_draft",
            target_id=draft_id,
            domain_version=domain_version,
            execution_backend="celery",
            provider="google_gemini",
            model_name=settings.gemini_model_name,
            model_version=settings.gemini_model_name,
            prompt_template_id="adoption-suitability",
            prompt_version="1",
            output_schema_version="1",
            status="pending_enqueue",
            retry_count=0,
            created_at=now,
            updated_at=now,
        )
    )


async def reconcile_ai_jobs(repository: AIJobRepository) -> list[AIProcessingJob]:
    """Return jobs that need a safe enqueue retry; caller owns the transaction."""
    jobs = await repository.pending_reconciliation()
    for job in jobs:
        if job.status == "enqueue_failed":
            job.status = "pending_enqueue"
    return jobs
