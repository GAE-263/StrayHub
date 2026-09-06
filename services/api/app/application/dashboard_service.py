from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.application.care_agenda_service import CareAgendaService
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.models.care_report_draft import CareReportDraft

ANOMALY_ATTENTION_LEVELS = ("urgent", "review")
ANOMALY_LOOKBACK_DAYS = 14
ANOMALY_LIMIT = 10
TODAY_SPECIAL_CARE_LIMIT = 10


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _recent_anomalies(self, *, organization_id: UUID) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=ANOMALY_LOOKBACK_DAYS)
        rows = (
            await self.session.execute(
                select(CareReport, Animal.name, Animal.shelter_number)
                .join(Animal, Animal.id == CareReport.animal_id)
                .where(
                    CareReport.organization_id == organization_id,
                    CareReport.attention_level.in_(ANOMALY_ATTENTION_LEVELS),
                    CareReport.submitted_at >= since,
                )
                .order_by(CareReport.submitted_at.desc())
            )
        ).all()
        urgency_rank = {"urgent": 2, "review": 1}
        rows.sort(
            key=lambda row: (urgency_rank.get(row[0].attention_level, 0), row[0].submitted_at),
            reverse=True,
        )
        seen_animal_ids: set[UUID] = set()
        anomalies: list[dict] = []
        for report, animal_name, shelter_number in rows:
            if report.animal_id in seen_animal_ids:
                continue
            seen_animal_ids.add(report.animal_id)
            anomalies.append(
                {
                    "animal_id": str(report.animal_id),
                    "animal_name": animal_name,
                    "animal_shelter_number": shelter_number,
                    "report_id": str(report.id),
                    "attention_level": report.attention_level,
                    "submitted_at": report.submitted_at.isoformat(),
                }
            )
            if len(anomalies) >= ANOMALY_LIMIT:
                break
        return anomalies

    async def _today_special_care(self, *, context: RequestContext) -> list[dict]:
        try:
            agenda = await CareAgendaService(self.session, context).build(
                page_size=TODAY_SPECIAL_CARE_LIMIT
            )
        except DomainError:
            # Staff without medical-care access simply see no widget content;
            # the dashboard itself must still render for them.
            return []
        items = [*agenda["buckets"]["overdue"], *agenda["buckets"]["today_pending"]]
        items.sort(key=lambda item: str(item["scheduled_at"]))
        return items[:TODAY_SPECIAL_CARE_LIMIT]

    async def summary(self, *, context: RequestContext) -> dict:
        organization_id = context.organization_id
        role = context.role
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
                select(CareReport, Animal.name, Animal.shelter_number)
                .join(Animal, Animal.id == CareReport.animal_id)
                .where(CareReport.organization_id == organization_id)
                .order_by(CareReport.submitted_at.desc())
                .limit(20)
            )
        ).all()
        recent_anomalies = await self._recent_anomalies(organization_id=organization_id)
        today_special_care = await self._today_special_care(context=context)
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
                    "animal_name": animal_name,
                    "animal_shelter_number": shelter_number,
                    "submitted_at": report.submitted_at.isoformat(),
                    "status": report.status,
                    "ai_job_status": report.ai_job_status,
                }
                for report, animal_name, shelter_number in recent
            ],
            "recent_anomalies": recent_anomalies,
            "today_special_care": today_special_care,
        }
