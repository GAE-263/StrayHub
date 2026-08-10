from __future__ import annotations

from datetime import datetime, time, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.models.care_report_draft import CareReportDraft


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self, *, organization_id: UUID, role: str) -> dict:
        start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
        end = datetime.combine(datetime.now(timezone.utc).date(), time.max, tzinfo=timezone.utc)
        animal_count = await self.session.scalar(
            select(func.count(Animal.id)).where(
                Animal.organization_id == organization_id,
                Animal.status == "active",
            )
        )
        today_report_count = await self.session.scalar(
            select(func.count(CareReport.id)).where(
                CareReport.organization_id == organization_id,
                CareReport.submitted_at >= start,
                CareReport.submitted_at <= end,
            )
        )
        draft_count = await self.session.scalar(
            select(func.count(CareReportDraft.id)).where(
                CareReportDraft.organization_id == organization_id,
                CareReportDraft.status == "active",
            )
        )
        ai_pending_count = await self.session.scalar(
            select(func.count(AIProcessingJob.id)).where(
                AIProcessingJob.organization_id == organization_id,
                AIProcessingJob.status.in_(
                    ["pending", "pending_enqueue", "enqueue_failed", "retry_wait", "running"]
                ),
            )
        )
        recent = (
            await self.session.execute(
                select(CareReport)
                .where(CareReport.organization_id == organization_id)
                .order_by(CareReport.submitted_at.desc())
                .limit(5)
            )
        ).scalars()
        return {
            "organization_id": str(organization_id),
            "role": role,
            "summary": {
                "reportable_animal_count": int(animal_count or 0),
                "today_report_count": int(today_report_count or 0),
                "active_draft_count": int(draft_count or 0),
                "pending_ai_count": int(ai_pending_count or 0),
                "alerts": [],
            },
            "recent_reports": [
                {
                    "id": str(report.id),
                    "animal_id": str(report.animal_id),
                    "submitted_at": report.submitted_at.isoformat(),
                    "status": report.status,
                    "ai_job_status": report.ai_job_status,
                }
                for report in recent
            ],
        }
