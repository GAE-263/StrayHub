from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AIObservation
from services.api.app.persistence.models.care_report import CareReport, CareReportMedia, MediaAsset
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.medical_care import (
    CareReminderAction,
    CareReminderOccurrence,
    CareReminderSeries,
    MedicalRecord,
)
from services.api.app.persistence.models.volunteer_management import VolunteerProfile


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

    async def volunteer_labels(
        self, membership_ids: list[UUID]
    ) -> dict[UUID, tuple[str | None, str | None]]:
        """Resolve canonical surname and shelter number for scoped memberships."""
        if not membership_ids:
            return {}
        result = await self.session.execute(
            select(
                OrganizationMembership.id,
                VolunteerProfile.surname,
                OrganizationMembership.volunteer_no,
            )
            .outerjoin(
                VolunteerProfile,
                VolunteerProfile.user_id == OrganizationMembership.user_id,
            )
            .where(
                OrganizationMembership.id.in_(set(membership_ids)),
                OrganizationMembership.organization_id == self.organization_id,
            )
        )
        return {
            membership_id: (surname, volunteer_no)
            for membership_id, surname, volunteer_no in result.all()
        }

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

    async def stool_analyses_for_reports(self, report_ids: list[UUID]) -> dict[UUID, dict]:
        """Return the latest valid stool payload for each already-scoped report."""
        if not report_ids:
            return {}
        result = await self.session.execute(
            select(AIProcessingJob.target_id, AIObservation)
            .join(AIProcessingJob, AIProcessingJob.id == AIObservation.job_id)
            .where(
                AIObservation.organization_id == self.organization_id,
                AIProcessingJob.organization_id == self.organization_id,
                AIProcessingJob.target_type == "care_report",
                AIProcessingJob.target_id.in_(report_ids),
            )
            .order_by(AIObservation.created_at, AIObservation.id)
        )
        analyses: dict[UUID, dict] = {}
        for report_id, observation in result.all():
            analysis = _stool_analysis_payload(observation)
            if analysis is not None:
                # The deterministic ascending query means a later valid retry
                # replaces an earlier one, including equal-timestamp rows.
                analyses[report_id] = analysis
        return analyses

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


def _stool_analysis_payload(observation: AIObservation) -> dict | None:
    payload = observation.raw_ai_output
    if not isinstance(payload, dict) or not isinstance(payload.get("recognized"), bool):
        return None

    score = payload.get("score")
    if score is not None and (
        not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 7
    ):
        return None
    has_abnormalities = payload.get("has_abnormalities", False)
    if not isinstance(has_abnormalities, bool) or (
        payload["recognized"] and "has_abnormalities" not in payload
    ):
        return None
    nullable_text_fields = (
        "score_label",
        "consistency",
        "abnormality_details",
        "assessment",
        "recommendation",
    )
    if any(
        payload.get(field) is not None and not isinstance(payload.get(field), str)
        for field in nullable_text_fields
    ):
        return None

    return {
        "recognized": payload["recognized"],
        "score": score,
        "score_label": payload.get("score_label") or payload.get("consistency"),
        "has_abnormalities": has_abnormalities,
        "abnormality_details": payload.get("abnormality_details"),
        "assessment": payload.get("assessment"),
        "recommendation": payload.get("recommendation"),
        "review_status": observation.status,
        "human_reviewed": observation.human_review_result is not None,
    }
