from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.care_report import CareReport, CareReportMedia, MediaAsset
from services.api.app.persistence.models.medical_care import (
    CareReminderAction,
    CareReminderOccurrence,
    CareReminderSeries,
    MedicalRecord,
)


class TimelineRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def reports(
        self, *, animal_id: UUID, start_date: date, end_date: date, timezone_name: str = "UTC"
    ) -> list[CareReport]:
        zone = ZoneInfo(timezone_name)
        start = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(timezone.utc)
        # Half-open range prevents precision-dependent omissions at day end.
        end = datetime.combine(end_date, time.min, tzinfo=zone).astimezone(timezone.utc)
        end = end.replace(microsecond=0)
        from datetime import timedelta

        end += timedelta(days=1)
        result = await self.session.execute(
            select(CareReport)
            .where(
                CareReport.organization_id == self.organization_id,
                CareReport.animal_id == animal_id,
                CareReport.submitted_at >= start,
                CareReport.submitted_at < end,
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

    async def medical_records(
        self, *, animal_id: UUID, start_date: date, end_date: date, timezone_name: str
    ) -> list[MedicalRecord]:
        start, end = self._local_bounds(start_date, end_date, timezone_name)
        result = await self.session.execute(
            select(MedicalRecord)
            .where(
                MedicalRecord.organization_id == self.organization_id,
                MedicalRecord.animal_id == animal_id,
                MedicalRecord.status == "active",
                MedicalRecord.occurred_at >= start,
                MedicalRecord.occurred_at < end,
            )
            .order_by(MedicalRecord.occurred_at, MedicalRecord.id)
        )
        return list(result.scalars())

    async def reminder_actions(
        self, *, animal_id: UUID, start_date: date, end_date: date, timezone_name: str
    ) -> list[CareReminderAction]:
        start, end = self._local_bounds(start_date, end_date, timezone_name)
        result = await self.session.execute(
            select(CareReminderAction)
            .join(CareReminderSeries, CareReminderSeries.id == CareReminderAction.series_id)
            .where(
                CareReminderAction.organization_id == self.organization_id,
                CareReminderSeries.animal_id == animal_id,
                CareReminderAction.acted_at >= start,
                CareReminderAction.acted_at < end,
            )
            .order_by(CareReminderAction.acted_at, CareReminderAction.id)
        )
        return list(result.scalars())

    async def active_reminder_sources(
        self, *, animal_id: UUID
    ) -> tuple[list[CareReminderSeries], dict[UUID, CareReminderOccurrence]]:
        series_result = await self.session.execute(
            select(CareReminderSeries).where(
                CareReminderSeries.organization_id == self.organization_id,
                CareReminderSeries.animal_id == animal_id,
                CareReminderSeries.status == "active",
            )
        )
        series = list(series_result.scalars())
        occurrence_result = (
            await self.session.execute(
                select(CareReminderOccurrence).where(
                    CareReminderOccurrence.organization_id == self.organization_id,
                    CareReminderOccurrence.series_id.in_([item.id for item in series]),
                )
            )
            if series
            else None
        )
        occurrences = (
            {item.id: item for item in occurrence_result.scalars()}
            if occurrence_result is not None
            else {}
        )
        return series, occurrences

    @staticmethod
    def _local_bounds(
        start_date: date, end_date: date, timezone_name: str
    ) -> tuple[datetime, datetime]:
        zone = ZoneInfo(timezone_name)
        start = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(timezone.utc)
        end = datetime.combine(end_date, time.min, tzinfo=zone).astimezone(timezone.utc)
        return start, end + timedelta(days=1)
