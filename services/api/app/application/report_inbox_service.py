from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AIObservation
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReport, CareReportMedia, MediaAsset


class ReportInboxService:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @staticmethod
    def payload(
        report: CareReport,
        *,
        animal: Animal | None = None,
        media_ids: list[str] | None = None,
    ) -> dict:
        return {
            "id": str(report.id),
            "organization_id": str(report.organization_id),
            "animal_id": str(report.animal_id),
            "animal_name": animal.name if animal else report.animal_name_snapshot,
            "animal_name_snapshot": report.animal_name_snapshot,
            "shelter_number_snapshot": report.shelter_number_snapshot,
            "volunteer_user_id": str(report.volunteer_user_id),
            "membership_id": str(report.membership_id),
            "answers": report.answers,
            "observations": report.answers,
            "answer_snapshots": report.answer_snapshots,
            "note": report.note,
            "status": report.status,
            "ai_job_status": report.ai_job_status,
            "submitted_at": report.submitted_at.isoformat(),
            "archived_at": report.archived_at.isoformat() if report.archived_at else None,
            "media_ids": media_ids or [],
        }

    async def list(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        animal_id: UUID | None,
        report_status: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        filters = [CareReport.organization_id == self.organization_id]
        if from_date:
            filters.append(
                CareReport.submitted_at
                >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
            )
        if to_date:
            filters.append(
                CareReport.submitted_at <= datetime.combine(to_date, time.max, tzinfo=timezone.utc)
            )
        if animal_id:
            filters.append(CareReport.animal_id == animal_id)
        if report_status:
            filters.append(CareReport.status == report_status)
        total = await self.session.scalar(select(func.count(CareReport.id)).where(*filters))
        rows = await self.session.execute(
            select(CareReport, Animal)
            .join(
                Animal,
                and_(
                    Animal.id == CareReport.animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .where(*filters)
            .order_by(CareReport.submitted_at.desc(), CareReport.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [self.payload(report, animal=animal) for report, animal in rows.all()],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }

    async def detail(self, report_id: UUID) -> dict:
        row = await self.session.execute(
            select(CareReport, Animal)
            .join(
                Animal,
                and_(
                    Animal.id == CareReport.animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .where(
                CareReport.id == report_id,
                CareReport.organization_id == self.organization_id,
            )
        )
        pair = row.one_or_none()
        if pair is None:
            raise DomainError("report_not_found", "照護回報不存在或無法存取", 404)
        report, animal = pair
        media = await self.session.execute(
            select(MediaAsset)
            .join(CareReportMedia, CareReportMedia.media_asset_id == MediaAsset.id)
            .where(
                CareReportMedia.report_id == report_id,
                MediaAsset.organization_id == self.organization_id,
            )
        )
        ai = await self.session.execute(
            select(AIObservation, AIProcessingJob)
            .join(AIProcessingJob, AIProcessingJob.id == AIObservation.job_id)
            .where(
                AIObservation.organization_id == self.organization_id,
                AIProcessingJob.organization_id == self.organization_id,
                AIProcessingJob.target_type == "care_report",
                AIProcessingJob.target_id == report_id,
            )
        )
        payload = self.payload(
            report,
            animal=animal,
            media_ids=[str(item.id) for item in media.scalars()],
        )
        payload["ai_observations"] = [
            {
                "id": str(observation.id),
                "status": observation.status,
                "source_type": observation.source_type,
                "source_id": str(observation.source_id) if observation.source_id else None,
                "raw_ai_output": observation.raw_ai_output,
                "validated_ai_observation": observation.validated_ai_observation,
                "human_review_result": observation.human_review_result,
                "failure_reason": job.failure_reason,
            }
            for observation, job in ai.all()
        ]
        return payload
