# ruff: noqa: B008
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.assigned_care_service import (
    AssignedCareItem,
    AssignedCareMutation,
    AssignedCareService,
)
from services.api.app.application.medical_care_audit import medical_care_audit_lifecycle
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Assigned Care"])


class AssignedCareAnimalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    shelter_number: str | None
    photo_url: str | None


class AssignedCareItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurrence_id: UUID
    version: int
    status: Literal["pending", "completed", "skipped", "cancelled"]
    animal: AssignedCareAnimalResponse
    reminder_type: str
    title: str
    instructions: str
    display_local_at: str
    can_complete: bool
    can_skip: bool


class AssignedCareListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AssignedCareItemResponse]
    next_cursor: str | None = None


class AssignedCareActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["complete", "skip"]
    expected_version: int = Field(ge=0)
    actual_completed_at: datetime | None = None
    result_note: str | None = Field(default=None, max_length=5000)
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_action_fields(self) -> AssignedCareActionRequest:
        if self.action == "skip" and not (self.reason or "").strip():
            raise ValueError("略過指派事項需要填寫原因")
        if self.action != "complete" and self.actual_completed_at is not None:
            raise ValueError("只有完成指派事項可以填寫實際完成時間")
        return self


class AssignedCareMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurrence: AssignedCareItemResponse
    action_id: UUID
    action_type: Literal["completed", "skipped"]
    acted_at: datetime
    recorded_at: datetime | None
    actual_completed_at: datetime | None


def _item_response(item: AssignedCareItem) -> AssignedCareItemResponse:
    return AssignedCareItemResponse(
        occurrence_id=item.occurrence_id,
        version=item.version,
        status=item.status,
        animal=AssignedCareAnimalResponse(
            id=item.animal.id,
            name=item.animal.name,
            shelter_number=item.animal.shelter_number,
            photo_url=item.animal.photo_url,
        ),
        reminder_type=item.reminder_type,
        title=item.title,
        instructions=item.instructions,
        display_local_at=item.display_local_at,
        can_complete=item.can_complete,
        can_skip=item.can_skip,
    )


def _mutation_response(result: AssignedCareMutation) -> AssignedCareMutationResponse:
    return AssignedCareMutationResponse(
        occurrence=_item_response(result.occurrence),
        action_id=result.action_id,
        action_type=result.action_type,
        acted_at=result.acted_at,
        recorded_at=result.recorded_at,
        actual_completed_at=result.actual_completed_at,
    )


def _required_scope(context: RequestContext) -> UUID:
    if context.organization_id is None:
        raise DomainError("assigned_care_not_found", "指派事項不存在或無法存取", 404)
    return context.organization_id


@router.get("/v1/assigned-care-reminders", response_model=AssignedCareListResponse)
async def list_assigned_care(
    cursor: str | None = None,
    page_size: int = Query(default=50, ge=1, le=100),
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> AssignedCareListResponse:
    organization_id = _required_scope(context)
    try:
        offset = int(cursor or "0")
        if offset < 0:
            raise ValueError
    except ValueError as exc:
        raise DomainError("assigned_care_cursor_invalid", "指派事項游標無效", 422) from exc
    async with medical_care_audit_lifecycle(
        session,
        organization_id=organization_id,
        actor_user_id=context.user_id,
        action="assigned_care.list",
        resource_type="CareReminderOccurrence",
    ):
        items = await AssignedCareService(session, context).list()
    page = items[offset : offset + page_size]
    next_offset = offset + len(page)
    return AssignedCareListResponse(
        items=[_item_response(item) for item in page],
        next_cursor=str(next_offset) if next_offset < len(items) else None,
    )


@router.get(
    "/v1/assigned-care-reminders/{occurrenceId}",
    response_model=AssignedCareItemResponse,
)
async def get_assigned_care(
    occurrenceId: UUID,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> AssignedCareItemResponse:  # noqa: N803
    organization_id = _required_scope(context)
    async with medical_care_audit_lifecycle(
        session,
        organization_id=organization_id,
        actor_user_id=context.user_id,
        action="assigned_care.read",
        resource_type="CareReminderOccurrence",
        resource_id=occurrenceId,
    ):
        item = await AssignedCareService(session, context).get(occurrenceId)
    return _item_response(item)


@router.post(
    "/v1/assigned-care-reminders/{occurrenceId}/actions",
    response_model=AssignedCareMutationResponse,
)
async def act_on_assigned_care(
    occurrenceId: UUID,
    payload: AssignedCareActionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> AssignedCareMutationResponse:  # noqa: N803
    if not idempotency_key:
        raise DomainError("idempotency_key_required", "請提供 Idempotency-Key", 422)
    organization_id = _required_scope(context)
    async with medical_care_audit_lifecycle(
        session,
        organization_id=organization_id,
        actor_user_id=context.user_id,
        action="assigned_care.action",
        resource_type="CareReminderOccurrence",
        resource_id=occurrenceId,
        reason=payload.reason,
    ):
        result = await AssignedCareService(session, context).act(
            occurrenceId,
            action=payload.action,
            expected_version=payload.expected_version,
            reason=payload.reason,
            result_note=payload.result_note,
            actual_completed_at=payload.actual_completed_at,
            idempotency_key=idempotency_key,
        )
    return _mutation_response(result)
