from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from services.api.app.application.ai_job_dispatch import create_ai_job
from services.api.app.application.celery_job_dispatch import dispatch_ai_job
from services.api.app.config.settings import get_settings
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.repositories.ai_job_repository import AIJobRepository


class ReportJobDispatchService:
    """在 Report 已提交後，以獨立交易建立可追蹤的 AI Job。"""

    def __init__(self, session_factory, *, ai_enabled: bool | None = None) -> None:
        self.session_factory = session_factory
        self.ai_enabled = ai_enabled

    def _enabled(self) -> bool:
        return self.ai_enabled if self.ai_enabled is not None else get_settings().celery_ai_enabled

    async def dispatch(self, *, organization_id: UUID, report_id: UUID) -> bool:
        if not self._enabled():
            return True
        try:
            job_ids: list[UUID] = []
            async with self.session_factory() as session:
                async with session.begin():
                    await set_organization_scope(session, organization_id)
                    result = await session.execute(
                        select(CareReport).where(
                            CareReport.id == report_id,
                            CareReport.organization_id == organization_id,
                        )
                    )
                    report = result.scalar_one_or_none()
                    if report is None:
                        return False
                    existing = await session.execute(
                        select(AIProcessingJob.id).where(
                            AIProcessingJob.organization_id == organization_id,
                            AIProcessingJob.target_id == report.id,
                            AIProcessingJob.job_type == "care_report_summary",
                        )
                    )
                    job_ids.extend(existing.scalars())
                    observation = await create_ai_job(
                        AIJobRepository(session, organization_id),
                        target_type="care_report",
                        target_id=report.id,
                    )
                    job_ids.append(observation.id)
                    report.ai_job_status = "enqueued"
            results = [await dispatch_ai_job(job_id, organization_id) for job_id in job_ids]
            return bool(results) and all(results)
        except Exception:
            await self._mark_failed(organization_id=organization_id, report_id=report_id)
            return False

    async def reconcile(self, *, organization_id: UUID, report_id: UUID) -> bool:
        """Retry an enqueue without recreating the already-saved report."""
        if not self._enabled():
            return True
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    await set_organization_scope(session, organization_id)
                    result = await session.execute(
                        select(CareReport).where(
                            CareReport.id == report_id,
                            CareReport.organization_id == organization_id,
                        )
                    )
                    report = result.scalar_one_or_none()
                    if report is None:
                        return False
                    if report.ai_job_status == "enqueued":
                        return True
                    await create_ai_job(
                        AIJobRepository(session, organization_id),
                        target_type="care_report",
                        target_id=report.id,
                    )
                    report.ai_job_status = "enqueued"
            return True
        except Exception:
            await self._mark_failed(organization_id=organization_id, report_id=report_id)
            return False

    async def _mark_failed(self, *, organization_id: UUID, report_id: UUID) -> None:
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    await set_organization_scope(session, organization_id)
                    result = await session.execute(
                        select(CareReport).where(
                            CareReport.id == report_id,
                            CareReport.organization_id == organization_id,
                        )
                    )
                    report = result.scalar_one_or_none()
                    if report is not None:
                        report.ai_job_status = "enqueue_failed"
        except Exception:
            # The saved Care Report remains the source of truth; reconciliation
            # can retry the status update or job creation later.
            return
