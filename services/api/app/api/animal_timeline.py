from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.timeline_service import TimelineService
from services.api.app.domain.care_recurrence import nth_local, occurrence_at, occurrence_id
from services.api.app.domain.organization_timezone import local_today
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.timeline_repository import TimelineRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Timeline"])


class TimelineEventResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    kind: str
    occurrence: Literal["actual", "scheduled"]
    title: str
    summary: str | None = None
    happened_at: str | None = None
    scheduled_at: str | None = None
    status: str | None = None


class TimelineDayResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: date
    has_report: bool
    report_count: int
    no_report_label: str | None = None
    has_activity: bool
    event_count: int
    reports: list[dict]
    events: list[TimelineEventResponse]
    scheduled: list[TimelineEventResponse]


class TimelineResponse(BaseModel):
    animal_id: UUID
    organization_timezone: str
    days: list[TimelineDayResponse]
    open_reminders: list[TimelineEventResponse]


def _serialize_day(
    day, *, media_by_report: dict | None = None, stool_by_report: dict | None = None
) -> dict:
    return {
        "date": day.date.isoformat(),
        "has_report": day.has_report,
        "report_count": day.report_count,
        "no_report_label": None if day.has_report else "當日無回報",
        "reports": [
            {
                "id": str(report.id),
                "submitted_at": report.submitted_at.isoformat(),
                "volunteer_user_id": str(report.volunteer_user_id),
                "animal_name_snapshot": report.animal_name_snapshot,
                "shelter_number_snapshot": report.shelter_number_snapshot,
                "note": report.note,
                "observations": report.answers,
                "observation_snapshots": report.answer_snapshots,
                "status": report.status,
                "ai_job_status": report.ai_job_status,
                "stool_analysis": (stool_by_report or {}).get(report.id),
                "media_ids": [
                    str(media.id) for media in (media_by_report or {}).get(report.id, [])
                ],
            }
            for report in day.reports
        ],
        "has_activity": bool(
            day.reports or getattr(day, "events", []) or getattr(day, "scheduled", [])
        ),
        "event_count": len(getattr(day, "events", [])),
        "events": getattr(day, "events", []),
        "scheduled": getattr(day, "scheduled", []),
    }


@router.get("/v1/animals/{animalId}/timeline", response_model=TimelineResponse)
async def animal_timeline(
    animalId: UUID,  # noqa: N803
    start_date: date | None = Query(None),  # noqa: B008
    end_date: date | None = Query(None),  # noqa: B008
    _context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    # The organization scope comes from the verified request context, never
    # from a query parameter or path segment.
    context = _context
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    if context.role not in {"PLATFORM_ADMIN", "SHELTER_ADMIN", "STAFF"}:
        raise DomainError("timeline_access_denied", "目前帳號無法查看完整歷程", 403)
    animal = await AnimalRepository(session, context.organization_id).get(animalId)
    if animal is None:
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    organization = (
        await session.execute(
            select(Organization).where(Organization.id == context.organization_id)
        )
    ).scalar_one()
    local_zone = ZoneInfo(organization.timezone)
    service = TimelineService(TimelineRepository(session, context.organization_id))
    days = (
        await service.date_range(
            animal_id=animalId,
            start_date=start_date,
            end_date=end_date,
            timezone_name=organization.timezone,
        )
        if start_date is not None and end_date is not None
        else await service.recent(
            animal_id=animalId,
            end_date=end_date,
            timezone_name=organization.timezone,
        )
    )
    if start_date is None:
        start_date = days[0].date
    if end_date is None:
        end_date = days[-1].date
    repository = TimelineRepository(session, context.organization_id)
    medical_records = await repository.medical_records(
        animal_id=animalId,
        start_date=start_date,
        end_date=end_date,
        timezone_name=organization.timezone,
    )
    records_by_date: dict[date, list[dict[str, str | None]]] = {}
    for record in medical_records:
        local_occurred = record.occurred_at.astimezone(local_zone)
        records_by_date.setdefault(local_occurred.date(), []).append(
            {
                "id": str(record.id),
                "kind": "medical_record",
                "occurrence": "actual",
                "happened_at": record.occurred_at.isoformat(),
                "display_local_at": local_occurred.isoformat(),
                "title": record.title,
                "summary": record.content,
            }
        )
    for day in days:
        day.events.extend(records_by_date.get(day.date, []))
    series_rows, occurrence_rows = await repository.active_reminder_sources(animal_id=animalId)
    relevant_occurrence_ids = {
        occurrence_id(series.lineage_id, index)
        for series in series_rows
        for index in range(0, 367)
        if index >= series.start_ordinal
        and (series.end_ordinal is None or index <= series.end_ordinal)
    }
    occurrence_rows = {
        key: value for key, value in occurrence_rows.items() if key in relevant_occurrence_ids
    }
    actions = await repository.reminder_actions(
        animal_id=animalId,
        start_date=start_date,
        end_date=end_date,
        timezone_name=organization.timezone,
    )
    days_by_date = {day.date: day for day in days}
    range_start, range_end = days[0].date, days[-1].date
    for series in series_rows:
        for index in range(0, 367):
            if index < series.start_ordinal:
                continue
            if series.end_ordinal is not None and index > series.end_ordinal:
                break
            nominal = nth_local(series.anchor_local_date, series.frequency, series.interval, index)
            if series.frequency == "none" and index > 0:
                break
            if series.end_local_date and nominal > series.end_local_date:
                break
            if nominal > range_end:
                break
            if nominal < range_start:
                continue
            oid = occurrence_id(series.lineage_id, index)
            persisted = occurrence_rows.get(oid)
            if persisted and persisted.status != "pending":
                continue
            scheduled = (
                persisted.scheduled_at
                if persisted
                else occurrence_at(
                    series.anchor_local_date,
                    series.anchor_local_time,
                    series.frequency,
                    series.interval,
                    index,
                    organization.timezone,
                )
            )
            local_scheduled = scheduled.astimezone(local_zone)
            day = days_by_date.get(local_scheduled.date())
            if day is not None:
                day.scheduled.append(
                    {
                        "id": str(oid),
                        "kind": "care_reminder",
                        "occurrence": "scheduled",
                        "status": "overdue"
                        if local_scheduled.date() < local_today(organization.timezone)
                        else "pending",
                        "scheduled_at": scheduled.isoformat(),
                        "title": persisted.title_snapshot if persisted else series.title,
                        "summary": persisted.instructions_snapshot
                        if persisted
                        else series.instructions,
                    }
                )
    for action in actions:
        action_day = action.acted_at.astimezone(local_zone).date()
        day = days_by_date.get(action_day)
        if day is not None:
            day.events.append(
                {
                    "id": str(action.id),
                    "kind": "care_reminder_action",
                    "occurrence": "actual",
                    "happened_at": action.acted_at.isoformat(),
                    "title": f"照護提醒{action.action_type}",
                    "summary": action.reason or action.result_note or "",
                }
            )
    report_ids = [report.id for day in days for report in day.reports]
    media_by_report = await repository.media_for_reports(report_ids)
    stool_by_report = await repository.stool_analyses_for_reports(report_ids)
    return {
        "days": [
            _serialize_day(day, media_by_report=media_by_report, stool_by_report=stool_by_report)
            for day in days
        ],
        "animal_id": str(animalId),
        "organization_timezone": organization.timezone,
        "open_reminders": [item for day in days for item in day.scheduled],
    }
