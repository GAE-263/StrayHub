# ruff: noqa: B008
from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.care_agenda_service import CareAgendaService
from services.api.app.application.care_reminder_service import CareReminderService
from services.api.app.application.medical_care_common import medical_permission
from services.api.app.domain.medical_care_access import require_medical_view, require_series_write
from services.api.app.domain.organization_timezone import validate_timezone
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.models.medical_care import (
    CareReminderSeries,
    ReminderFrequency,
    ReminderType,
)
from services.api.app.persistence.repositories.care_reminder_repository import (
    CareReminderRepository,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Care Reminders"])


class SeriesCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reminder_type: ReminderType
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=5000)
    first_execution_at: datetime
    assignee_membership_id: UUID | None = None
    frequency: ReminderFrequency = ReminderFrequency.NONE
    interval: int = Field(default=1, ge=1, le=120)
    end_local_date: date | None = None


class SeriesStopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class OccurrenceActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["completed", "skipped", "cancelled", "rescheduled"]
    expected_version: int = Field(default=0, ge=0)
    reason: str | None = Field(default=None, max_length=2000)
    result_note: str | None = Field(default=None, max_length=5000)
    scheduled_at: datetime | None = None
    actual_completed_at: datetime | None = None


class OccurrenceEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["this", "this_and_future"] = "this"
    expected_version: int = Field(ge=0)
    scheduled_at: datetime | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=5000)
    reason: str = Field(min_length=1, max_length=2000)


class SeriesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    lineage_id: UUID
    animal_id: UUID
    reminder_type: str
    title: str
    instructions: str
    assignee_membership_id: UUID | None
    anchor_local_date: date
    anchor_local_time: time
    frequency: str
    interval: int
    end_local_date: date | None
    status: str
    version: int


class OccurrenceResponse(BaseModel):
    id: UUID
    animal_id: UUID
    reminder_type: str
    title: str
    instructions: str
    scheduled_at: datetime
    status: str
    version: int
    is_virtual: bool


class OccurrenceMutationResponse(BaseModel):
    action_id: UUID
    action_type: str
    acted_at: datetime
    actor_user_id: UUID
    occurrence_id: UUID
    status: str
    version: int
    scheduled_at: datetime
    recorded_at: datetime | None
    actual_completed_at: datetime | None


class AgendaItemResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    occurrence_id: UUID
    animal_id: UUID
    animal_name: str
    shelter_number: str | None
    reminder_type: str
    title: str
    instructions: str
    scheduled_at: datetime
    status: str
    version: int
    is_virtual: bool
    assignee_membership_id: UUID | None


class CareAgendaResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    timezone: str
    timezone_version: int
    local_today: date
    buckets: dict[str, list[AgendaItemResponse]]
    totals: dict[str, int]
    pages: dict[str, CareAgendaBucketPageResponse]


class CareAgendaBucketPageResponse(BaseModel):
    items: list[AgendaItemResponse]
    total_count: int
    next_cursor: str | None


class CareCalendarResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    organization_timezone: str
    timezone_version: int
    date_from: date
    date_to: date
    days: list[dict[str, object]]
    total_count: int
    next_cursor: str | None


def _series_response(series: CareReminderSeries) -> SeriesResponse:
    return SeriesResponse.model_validate(series, from_attributes=True)


async def _permission(session: AsyncSession, context: RequestContext):
    permission = await medical_permission(session, context)
    require_medical_view(permission)
    return permission


@router.post(
    "/v1/management/animals/{animalId}/care-reminder-series",
    response_model=SeriesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_series(
    animalId: UUID,
    payload: SeriesCreateRequest,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> SeriesResponse:  # noqa: N803
    permission = await _permission(session, context)
    require_series_write(permission)
    organization = (
        await session.execute(
            select(Organization).where(Organization.id == context.organization_id)
        )
    ).scalar_one()
    first = (
        payload.first_execution_at
        if payload.first_execution_at.tzinfo
        else payload.first_execution_at.replace(
            tzinfo=ZoneInfo(validate_timezone(organization.timezone))
        )
    )
    local_first = first.astimezone(ZoneInfo(validate_timezone(organization.timezone)))
    service = CareReminderService(session, context)
    series = await service.create_series(
        animalId,
        {
            "reminder_type": payload.reminder_type.value,
            "title": payload.title,
            "instructions": payload.instructions,
            "first_execution_at": first,
            "anchor_local_date": local_first.date(),
            "anchor_local_time": local_first.time().replace(tzinfo=None),
            "assignee_membership_id": payload.assignee_membership_id,
            "frequency": payload.frequency.value,
            "interval": payload.interval,
            "end_local_date": payload.end_local_date,
        },
    )
    return _series_response(series)


@router.get("/v1/management/care-reminder-series/{seriesId}", response_model=SeriesResponse)
async def get_series(
    seriesId: UUID,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> SeriesResponse:  # noqa: N803
    await _permission(session, context)
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    series = await CareReminderRepository(session, context.organization_id).series(seriesId)
    if series is None:
        raise DomainError("reminder_series_not_found", "提醒不存在或無法存取", 404)
    return _series_response(series)


@router.post("/v1/management/care-reminder-series/{seriesId}/stop", response_model=SeriesResponse)
async def stop_series(
    seriesId: UUID,
    payload: SeriesStopRequest,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> SeriesResponse:  # noqa: N803
    permission = await _permission(session, context)
    require_series_write(permission)
    return _series_response(
        await CareReminderService(session, context).stop_series(
            seriesId, payload.expected_version, payload.reason
        )
    )


async def _agenda(
    context: RequestContext,
    session: AsyncSession,
    target_day: date | None = None,
    animal_id: UUID | None = None,
    reminder_type: str | None = None,
    assignee_membership_id: UUID | None = None,
    status_filter: str | None = None,
    page_size: int = 100,
    cursors: dict[str, int] | None = None,
) -> dict:
    return await CareAgendaService(session, context).build(
        target_day=target_day,
        animal_id=animal_id,
        reminder_type=reminder_type,
        assignee_membership_id=assignee_membership_id,
        status_filter=status_filter,
        page_size=page_size,
        cursors=cursors,
    )


@router.get("/v1/management/care-agenda", response_model=CareAgendaResponse)
async def get_care_agenda(
    date_value: date | None = Query(None, alias="date"),
    animal_id: UUID | None = None,
    reminder_type: str | None = None,
    assignee_membership_id: UUID | None = None,
    status: str | None = None,
    page_size: int = Query(100, ge=1, le=500),
    today_pending_cursor: int = Query(0, ge=0),
    overdue_cursor: int = Query(0, ge=0),
    today_resolved_cursor: int = Query(0, ge=0),
    next_seven_days_cursor: int = Query(0, ge=0),
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> dict:
    return await _agenda(
        context,
        session,
        date_value,
        animal_id,
        reminder_type,
        assignee_membership_id,
        status,
        page_size,
        {
            "today_pending": today_pending_cursor,
            "overdue": overdue_cursor,
            "today_resolved": today_resolved_cursor,
            "next_seven_days": next_seven_days_cursor,
        },
    )


@router.get("/v1/management/care-calendar", response_model=CareCalendarResponse)
async def get_care_calendar(
    date_from: date,
    date_to: date,
    animal_id: UUID | None = None,
    reminder_type: str | None = None,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> CareCalendarResponse:
    if date_to < date_from or (date_to - date_from).days > 366:
        raise DomainError("calendar_range_invalid", "行事曆查詢範圍最多 366 天", 422)
    return CareCalendarResponse.model_validate(
        await CareAgendaService(session, context).calendar(
            date_from=date_from,
            date_to=date_to,
            animal_id=animal_id,
            reminder_type=reminder_type,
        )
    )


@router.post(
    "/v1/management/care-reminder-occurrences/{occurrenceId}/actions",
    response_model=OccurrenceMutationResponse,
)
async def act_on_occurrence(
    occurrenceId: UUID,
    payload: OccurrenceActionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> OccurrenceMutationResponse:  # noqa: N803
    await _permission(session, context)
    if not idempotency_key:
        raise DomainError("idempotency_key_required", "請提供 Idempotency-Key", 422)
    result = await CareReminderService(session, context).act(
        occurrenceId,
        payload.action,
        payload.reason,
        payload.result_note,
        idempotency_key,
        {"scheduled_at": payload.scheduled_at, "actual_completed_at": payload.actual_completed_at},
        payload.expected_version,
    )
    occurrence = result.occurrence
    return OccurrenceMutationResponse(
        action_id=result.action.id,
        action_type=result.action.action_type,
        acted_at=result.action.acted_at,
        actor_user_id=result.action.actor_user_id,
        occurrence_id=occurrence.id,
        status=occurrence.status,
        version=occurrence.version,
        scheduled_at=occurrence.scheduled_at,
        recorded_at=occurrence.recorded_at,
        actual_completed_at=occurrence.actual_completed_at,
    )


@router.patch("/v1/management/care-reminder-occurrences/{occurrenceId}")
async def edit_occurrence(
    occurrenceId: UUID,
    payload: OccurrenceEditRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> dict:  # noqa: N803
    await _permission(session, context)
    if not idempotency_key:
        raise DomainError("idempotency_key_required", "請提供 Idempotency-Key", 422)
    occurrence = await CareReminderService(session, context).edit_occurrence(
        occurrenceId,
        scope=payload.scope,
        expected_version=payload.expected_version,
        scheduled_at=payload.scheduled_at,
        title=payload.title,
        instructions=payload.instructions,
        reason=payload.reason,
        idempotency_key=idempotency_key,
    )
    return {
        "occurrence_id": str(occurrence.id),
        "status": occurrence.status,
        "version": occurrence.version,
        "scheduled_at": occurrence.scheduled_at.isoformat(),
    }
