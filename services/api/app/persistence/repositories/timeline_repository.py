from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.care_report import CareReport, CareReportMedia, MediaAsset


class TimelineRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def reports(
        self, *, animal_id: UUID, start_date: date, end_date: date
    ) -> list[CareReport]:
        start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        result = await self.session.execute(
            select(CareReport)
            .where(
                CareReport.organization_id == self.organization_id,
                CareReport.animal_id == animal_id,
                CareReport.submitted_at >= start,
                CareReport.submitted_at <= end,
            )
            .order_by(CareReport.submitted_at, CareReport.id)
        )
        return list(result.scalars())

    async def media_for_reports(self, report_ids: list[UUID]) -> dict[UUID, list[MediaAsset]]:
        if not report_ids:
            return {}
        result = await self.session.execute(
            select(CareReportMedia.report_id, MediaAsset)
            .join(MediaAsset, MediaAsset.id == CareReportMedia.media_asset_id)
            .where(
                CareReportMedia.report_id.in_(report_ids),
                MediaAsset.organization_id == self.organization_id,
            )
        )
        media_by_report: dict[UUID, list[MediaAsset]] = {}
        for report_id, media in result.all():
            media_by_report.setdefault(report_id, []).append(media)
        return media_by_report
