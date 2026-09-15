"""Claim tenant-scoped AI jobs, build stool context, and persist safe outcomes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.app.config.settings import get_worker_settings
from services.api.app.domain.report_summary import build_prompt, fingerprint, validate_summary
from services.api.app.infrastructure.ai.gemini_client import GeminiClient
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope, ObjectStoragePort
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AIObservation
from services.api.app.persistence.models.care_report import CareReport, CareReportMedia, MediaAsset
from services.api.app.persistence.repositories.ai_observation_repository import (
    AIObservationRepository,
)
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.ai_adapter import AIAdapter
from services.worker.app.infrastructure.ai_port import AIClientPort
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter
from services.worker.app.infrastructure.stool_analysis_adapter import StoolAnalysisAdapter
from services.worker.app.persistence.job_repository import WorkerJobRepository

AI_STALE_TIMEOUT_SECONDS = 300
AI_MAX_RETRY = 3
AI_RETRY_BACKOFF_SECONDS = 60
AI_RETRY_BACKOFF_CAP_SECONDS = 900
AI_JOBS_PER_ITERATION = 20


def _retry_available_at(retry_count: int) -> datetime:
    delay = min(
        AI_RETRY_BACKOFF_SECONDS * 2 ** max(0, retry_count - 1),
        AI_RETRY_BACKOFF_CAP_SECONDS,
    )
    return datetime.now(timezone.utc) + timedelta(seconds=delay)


def build_ai_client() -> AIClientPort:
    settings = get_worker_settings()
    stool_key = settings.stool_api_key.get_secret_value() if settings.stool_api_key else None
    if settings.stool_api_url and stool_key:
        return StoolAnalysisAdapter(
            endpoint=settings.stool_api_url,
            api_key=stool_key,
            timeout_seconds=settings.stool_timeout_seconds,
        )
    if settings.ai_provider == "mock":
        return MockAIAdapter()
    return AIAdapter(
        endpoint=settings.ai_endpoint,
        api_key=settings.ai_api_key,
        timeout_seconds=settings.ai_timeout_seconds,
    )


class AIJobRunner:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        worker_id: str,
        client: AIClientPort,
        storage: ObjectStoragePort | None = None,
    ) -> None:
        self.factory = factory
        self.worker_id = worker_id
        self.client = client
        self._storage = storage

    @property
    def storage(self) -> ObjectStoragePort:
        if self._storage is None:
            self._storage = MinioStorageAdapter()
        return self._storage

    async def run_pending(
        self, organization_id: UUID, *, limit: int = AI_JOBS_PER_ITERATION
    ) -> int:
        bounded_limit = max(0, min(limit, AI_JOBS_PER_ITERATION))
        await self._reclaim_stale(organization_id)
        processed = 0
        for _ in range(bounded_limit):
            claimed = await self._claim(organization_id)
            if claimed is None:
                break
            job_id, claim_token = claimed
            await self._process(organization_id, job_id, claim_token)
            processed += 1
        return processed

    async def run_celery_job(
        self, organization_id: UUID, job_id: UUID, *, claim_token: str
    ) -> bool:
        async with self.factory() as session:
            claimed = await WorkerJobRepository(
                session, organization_id, worker_id=self.worker_id
            ).claim_celery(job_id, claim_token=claim_token)
            if not claimed:
                await session.rollback()
                return False
            await session.commit()
        await self._process(organization_id, job_id, claim_token)
        return True

    async def _reclaim_stale(self, organization_id: UUID) -> None:
        async with self.factory() as session:
            await WorkerJobRepository(
                session, organization_id, worker_id=self.worker_id
            ).reclaim_stale(
                timeout_seconds=AI_STALE_TIMEOUT_SECONDS,
                max_retries=AI_MAX_RETRY,
            )
            await session.commit()

    async def _claim(self, organization_id: UUID) -> tuple[UUID, str] | None:
        async with self.factory() as session:
            claimed = await WorkerJobRepository(
                session, organization_id, worker_id=self.worker_id
            ).claim_next()
            if claimed is None:
                await session.rollback()
                return None
            job, claim_token = claimed
            job_id = job.id
            await session.commit()
            return job_id, claim_token

    async def _process(self, organization_id: UUID, job_id: UUID, claim_token: str) -> None:
        try:
            async with self.factory() as session:
                await set_organization_scope(session, organization_id)
                job = await self._load_job(session, organization_id, job_id)
                if job is None:
                    return
                if job.job_type == "care_report_summary":
                    await self._summarize(session, organization_id, job, claim_token)
                    await session.commit()
                    return
                context = await self._load_context(session, organization_id, job)
                if context is None:
                    await self._finish(
                        session,
                        organization_id,
                        job_id,
                        claim_token,
                        status="failed",
                        failure_reason="ai_target_unavailable",
                    )
                    await session.commit()
                    return
                if not context.media_assets:
                    self._mark_no_stool_media(job, context)
                else:
                    await AIJobHandler(self.client).handle(
                        job,
                        note=context.report.note,
                        cleaned_images=context.images,
                        allowed_codes=context.allowed_codes,
                        observation=context.observation,
                        organization_id=organization_id,
                        report=context.report,
                        media_assets=context.media_assets,
                    )
                status, failure_reason = self._outcome(job)
                if status == "retry_wait":
                    context.report.ai_job_status = "enqueued"
                await self._finish(
                    session,
                    organization_id,
                    job_id,
                    claim_token,
                    status=status,
                    failure_reason=failure_reason,
                    retry_count=job.retry_count or 0,
                )
                await session.commit()
        except asyncio.CancelledError as error:
            await self._release_after_error(organization_id, job_id, claim_token, error)
            raise
        except Exception as error:
            await self._release_after_error(organization_id, job_id, claim_token, error)

    @staticmethod
    async def _summarize(session, organization_id, job, claim_token):
        # Lock job ownership for the complete bounded call; stale reclaim cannot
        # publish an obsolete response over a new owner.
        await session.refresh(job, with_for_update=True)
        if job.claim_token != claim_token or job.status != "running":
            return
        report = await session.scalar(
            select(CareReport)
            .where(
                CareReport.id == job.target_id,
                CareReport.organization_id == organization_id,
            )
            .with_for_update()
        )
        if report is None:
            job.status = "failed"
            job.failure_reason = "ai_target_unavailable"
        else:
            settings = get_worker_settings()
            raw = None
            if settings.gemini_configured:
                client = GeminiClient(
                    model_name=job.model_name,
                    api_key=settings.gemini_api_key,
                    service_account_path=settings.gemini_service_account_path,
                    location=settings.gemini_vertex_location,
                    use_runtime_identity=settings.gemini_use_runtime_identity,
                    project_id=settings.gemini_vertex_project,
                    runtime_service_account=settings.gemini_runtime_service_account,
                )
                try:
                    raw = await client.generate_report_summary(build_prompt(report))
                finally:
                    await client.aclose()
            job.raw_ai_output = raw
            try:
                if raw is None:
                    raise ValueError("model_unavailable")
                result = validate_summary(raw, report)
            except ValueError:
                job.retry_count = (job.retry_count or 0) + 1
                job.status = "retry_wait" if job.retry_count < AI_MAX_RETRY else "failed"
                job.failure_reason = "summary_unavailable_or_invalid"
                job.available_at = (
                    _retry_available_at(job.retry_count) if job.status == "retry_wait" else None
                )
                report.summary_status = "pending" if job.status == "retry_wait" else "failed"
            else:
                observation = await AIJobRunner._observation_for(session, organization_id, job)
                observation.source_type = "care_report_summary"
                observation.raw_ai_output = raw
                observation.validated_ai_observation = result
                observation.status = "succeeded"
                job.status = "succeeded"
                job.failure_reason = None
                job.validation_result = {"status": "valid", "fingerprint": fingerprint(report)}
                report.summary_data = result
                report.summary_fingerprint = fingerprint(report)
                report.summary_status = "succeeded"
                report.attention_level = result["attention_level"]
        job.completed_at = (
            datetime.now(timezone.utc) if job.status in {"failed", "succeeded"} else None
        )
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None

    @staticmethod
    async def _load_job(
        session: AsyncSession, organization_id: UUID, job_id: UUID
    ) -> AIProcessingJob | None:
        result = await session.execute(
            select(AIProcessingJob).where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def _load_context(
        self, session: AsyncSession, organization_id: UUID, job: AIProcessingJob
    ) -> _JobContext | None:
        if job.target_type != "care_report":
            return None
        report_result = await session.execute(
            select(CareReport).where(
                CareReport.id == job.target_id,
                CareReport.organization_id == organization_id,
            )
        )
        report = report_result.scalar_one_or_none()
        if report is None:
            return None
        media_result = await session.execute(
            select(MediaAsset)
            .join(CareReportMedia, CareReportMedia.media_asset_id == MediaAsset.id)
            .where(
                CareReportMedia.report_id == report.id,
                MediaAsset.organization_id == organization_id,
                MediaAsset.subject == "stool",
            )
            .order_by(MediaAsset.created_at, MediaAsset.id)
        )
        media_assets = list(media_result.scalars())
        images = [
            await self.storage.get(scope=ObjectScope(organization_id), key=asset.object_key)
            for asset in media_assets
        ]
        options = await ObservationRepository(session, organization_id).effective_options()
        observation = await self._observation_for(session, organization_id, job)
        return _JobContext(
            report=report,
            media_assets=media_assets,
            images=images,
            allowed_codes={option.code for option in options},
            observation=observation,
        )

    @staticmethod
    async def _observation_for(
        session: AsyncSession, organization_id: UUID, job: AIProcessingJob
    ) -> AIObservation:
        repository = AIObservationRepository(session, organization_id)
        existing = await repository.list_for_job(job.id)
        if existing:
            return existing[0]
        return await repository.add(
            AIObservation(
                organization_id=organization_id,
                job_id=job.id,
                source_type=job.target_type,
                source_id=job.target_id,
                status="pending",
            )
        )

    @staticmethod
    def _mark_no_stool_media(job: AIProcessingJob, context: _JobContext) -> None:
        raw = {"skipped": "no_stool_media"}
        formal: dict[str, list] = {"observations": []}
        job.raw_ai_output = raw
        job.validation_result = {"status": "valid", "outcome": "skipped"}
        job.failure_reason = None
        job.status = "succeeded"
        context.observation.raw_ai_output = raw
        context.observation.validated_ai_observation = formal
        context.observation.status = "succeeded"
        context.report.ai_job_status = "succeeded"

    @staticmethod
    def _outcome(job: AIProcessingJob) -> tuple[str, str | None]:
        if job.status == "succeeded":
            return "succeeded", None
        if job.status == "invalid":
            return "failed", job.failure_reason
        if (job.retry_count or 0) < AI_MAX_RETRY:
            return "retry_wait", job.failure_reason
        return "failed", job.failure_reason

    async def _finish(
        self,
        session: AsyncSession,
        organization_id: UUID,
        job_id: UUID,
        claim_token: str,
        *,
        status: str,
        failure_reason: str | None,
        retry_count: int = 0,
    ) -> None:
        await WorkerJobRepository(session, organization_id, worker_id=self.worker_id).finish(
            job_id,
            claim_token=claim_token,
            status=status,
            failure_reason=failure_reason,
            available_at=_retry_available_at(retry_count) if status == "retry_wait" else None,
        )

    async def _release_after_error(
        self,
        organization_id: UUID,
        job_id: UUID,
        claim_token: str,
        error: BaseException,
    ) -> None:
        failure_reason = getattr(error, "code", None) or type(error).__name__
        try:
            async with self.factory() as session:
                await set_organization_scope(session, organization_id)
                job = await self._load_job(session, organization_id, job_id)
                retry_count = (getattr(job, "retry_count", 0) or 0) + 1
                status = "retry_wait" if retry_count < AI_MAX_RETRY else "failed"
                if job is not None:
                    job.retry_count = retry_count
                    if job.job_type == "care_report_summary":
                        report = await session.scalar(
                            select(CareReport).where(
                                CareReport.id == job.target_id,
                                CareReport.organization_id == organization_id,
                            )
                        )
                        if report is not None:
                            report.summary_status = "failed" if status == "failed" else "pending"
                await self._finish(
                    session,
                    organization_id,
                    job_id,
                    claim_token,
                    status=status,
                    failure_reason=str(failure_reason)[:500],
                    retry_count=retry_count,
                )
                await session.commit()
        except Exception:
            return


class _JobContext:
    __slots__ = ("allowed_codes", "images", "media_assets", "observation", "report")

    def __init__(
        self,
        *,
        report: CareReport,
        media_assets: list[MediaAsset],
        images: list[bytes],
        allowed_codes: set[str],
        observation: AIObservation,
    ) -> None:
        self.report = report
        self.media_assets = media_assets
        self.images = images
        self.allowed_codes = allowed_codes
        self.observation = observation
