"""把 AI Job 從資料表帶到 AIJobHandler，再把結果寫回去。

AIJobHandler 只負責「呼叫供應商並判讀結果」，它拿到的是已經備妥的 job、
report、圖片位元組與允許的選項代碼。這個模組補上兩者之間的搬運：認領工作、
組裝上下文、保存 Observation、釋放 Claim。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope, ObjectStoragePort
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AIObservation
from services.api.app.persistence.models.care_report import (
    CareReport,
    CareReportMedia,
    MediaAsset,
)
from services.api.app.persistence.repositories.ai_observation_repository import (
    AIObservationRepository,
)
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.ai_adapter import AIAdapter
from services.worker.app.infrastructure.ai_port import AIClientPort
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter
from services.worker.app.persistence.job_repository import WorkerJobRepository

# 認領後超過這個時間仍是 running 的 Job 視為 Worker 中斷，交還給下一輪。
AI_STALE_TIMEOUT_SECONDS = 300
# 供應商錯誤重試上限；超過就標記 failed，不再無限重試。
AI_MAX_RETRY = 3
# 重試退避的基準與上限。沒有退避的話，供應商中斷時每筆 Job 會在同一輪內
# 把重試次數用光，等於沒有重試。
AI_RETRY_BACKOFF_SECONDS = 60
AI_RETRY_BACKOFF_CAP_SECONDS = 900
# 單一輪次處理的 Job 數上限，避免一個收容所的積壓餓死其他收容所。
AI_JOBS_PER_ITERATION = 20


def _retry_available_at(retry_count: int) -> datetime:
    delay = min(
        AI_RETRY_BACKOFF_SECONDS * 2 ** max(0, retry_count - 1),
        AI_RETRY_BACKOFF_CAP_SECONDS,
    )
    return datetime.now(timezone.utc) + timedelta(seconds=delay)


def build_ai_client() -> AIClientPort:
    """依設定選擇 AI 供應商；預設的 mock 讓本機展示不需要外部服務。"""
    settings = get_settings()
    if settings.ai_provider == "mock":
        return MockAIAdapter()
    return AIAdapter(
        endpoint=settings.ai_endpoint,
        api_key=settings.ai_api_key,
        timeout_seconds=settings.ai_timeout_seconds,
    )


class AIJobRunner:
    """以 Organization Scope 逐筆處理 AI Job。"""

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
        # 延後建立，讓沒有照片的流程不必連上物件儲存。
        if self._storage is None:
            self._storage = MinioStorageAdapter()
        return self._storage

    async def run_pending(
        self, organization_id: UUID, *, limit: int = AI_JOBS_PER_ITERATION
    ) -> int:
        await self._reclaim_stale(organization_id)
        processed = 0
        for _ in range(limit):
            claimed = await self._claim(organization_id)
            if claimed is None:
                break
            job_id, claim_token = claimed
            await self._process(organization_id, job_id, claim_token)
            processed += 1
        return processed

    async def _reclaim_stale(self, organization_id: UUID) -> None:
        async with self.factory() as session:
            await WorkerJobRepository(
                session, organization_id, worker_id=self.worker_id
            ).reclaim_stale(timeout_seconds=AI_STALE_TIMEOUT_SECONDS)
            await session.commit()

    async def _claim(self, organization_id: UUID) -> tuple[UUID, str] | None:
        """在獨立交易裡認領，讓後續的供應商呼叫不必持有資料列鎖。"""
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
                context = await self._load_context(session, organization_id, job)
                if context is None:
                    # 目標不存在或不是支援的類型；沒有可分析的內容，直接結案。
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
                    # Handler 已把回報標成失敗，但這筆還會再試一次，
                    # 對工作人員而言它仍在排隊中。
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
        except Exception as error:
            # 取圖、資料庫或供應商以外的任何失敗都不該讓 Claim 懸空，
            # 否則這筆 Job 要等到 stale timeout 才會回到佇列。
            await self._release_after_error(organization_id, job_id, claim_token, error)

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
            )
            .order_by(MediaAsset.created_at)
        )
        media_assets = list(media_result.scalars())
        scope = ObjectScope(organization_id)
        images = [
            await self.storage.get(scope=scope, key=asset.object_key) for asset in media_assets
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
        """重試時沿用同一列，避免同一個 Job 留下多筆待覆核的 Observation。"""
        repository = AIObservationRepository(session, organization_id)
        existing = await repository.list_for_job(job.id)
        if existing:
            return existing[0]
        return await repository.add(
            AIObservation(
                organization_id=organization_id,
                job_id=job.id,
                source_type=job.target_type,
                status="pending",
            )
        )

    @staticmethod
    def _outcome(job: AIProcessingJob) -> tuple[str, str | None]:
        if job.status == "succeeded":
            return "succeeded", None
        if job.status == "invalid":
            # 驗證失敗是決定性的：同樣的輸入重跑一次仍然不會通過。
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
                retry_count = (getattr(job, "retry_count", 0) or 0) if job else AI_MAX_RETRY
                status = "retry_wait" if retry_count < AI_MAX_RETRY else "failed"
                if job is not None:
                    job.retry_count = retry_count + 1
                await self._finish(
                    session,
                    organization_id,
                    job_id,
                    claim_token,
                    status=status,
                    failure_reason=failure_reason[:500],
                    retry_count=retry_count + 1,
                )
                await session.commit()
        except Exception:
            # 連釋放都失敗時交給 stale reclaim；照護回報本身已經保存，
            # AI 分析延後不影響它。
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
