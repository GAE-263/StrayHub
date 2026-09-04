from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError, ErrorResponse
from services.api.app.application.audit_service import AuditService
from services.api.app.application.volunteer_management_service import (
    VolunteerManagementService,
)
from services.api.app.domain.organization_timezone import local_today
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.volunteer_management_repository import (
    VolunteerManagementRepository,
)
from services.api.app.persistence.repositories.volunteer_service_summary_repository import (
    VolunteerServiceSummaryRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    tags=["Volunteer Management"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


class VolunteerStatisticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_shelter_visits: int = Field(ge=0)
    total_strayhub_visits: int = Field(ge=0)
    visits_last_180_days: int = Field(ge=0)
    visits_last_90_days: int = Field(ge=0)
    visits_last_30_days: int = Field(ge=0)
    last_visit_at: datetime | None
    active_months_last_6_months: int = Field(ge=0, le=6)
    recent_status: str


class VolunteerNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    content: str
    author_display_name: str
    created_at: datetime


class VolunteerIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    incident_type: str
    severity: Literal["low", "medium", "high", "critical"]
    factual_summary: str
    occurred_at: datetime
    status: Literal["reported", "under_review", "confirmed", "dismissed"]


class VolunteerRestrictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    scope: Literal["SHELTER", "PLATFORM"]
    reason_category: str
    status: Literal["pending_review", "active", "rejected", "expired", "revoked"]
    starts_at: datetime
    ends_at: datetime | None
    reviewed_at: datetime | None


class VolunteerProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership_id: UUID
    volunteer_no: str
    label: str
    surname: str | None
    membership_status: str
    can_assist_new_volunteers: bool
    statistics: VolunteerStatisticsResponse
    notes: list[VolunteerNoteResponse]
    incidents: list[VolunteerIncidentResponse]
    restrictions: list[VolunteerRestrictionResponse]


class VolunteerNoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)


class VolunteerAssistFlagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_assist_new_volunteers: bool


class VolunteerIncidentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_type: str = Field(min_length=1, max_length=80)
    severity: Literal["low", "medium", "high", "critical"]
    factual_summary: str = Field(min_length=1, max_length=2000)
    occurred_at: datetime


class VolunteerRestrictionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["SHELTER", "PLATFORM"]
    reason_category: str = Field(min_length=1, max_length=80)
    starts_at: datetime
    ends_at: datetime | None = None


class VolunteerIncidentDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirm", "dismiss"]


class PlatformRestrictionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=500)


class PlatformRestrictionReviewItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restriction: VolunteerRestrictionResponse
    incident: VolunteerIncidentResponse
    originating_organization_id: UUID
    originating_organization_name: str


def _context(value: RequestContext) -> TenantContext:
    return TenantContext(
        user_id=value.user_id,
        organization_id=value.organization_id,
        role=value.role,
        platform_scope=value.platform_scope,
    )


def _service(session: AsyncSession, organization_id: UUID) -> VolunteerManagementService:
    return VolunteerManagementService(
        VolunteerManagementRepository(session, organization_id),
        VolunteerServiceSummaryRepository(session, organization_id),
        AuditService(session),
    )


def _note_response(note, author_display_name: str) -> VolunteerNoteResponse:
    return VolunteerNoteResponse(
        id=note.id,
        content=note.content,
        author_display_name=author_display_name,
        created_at=note.created_at,
    )


def _restriction_response(restriction) -> VolunteerRestrictionResponse:
    return VolunteerRestrictionResponse.model_validate(restriction)


@router.get(
    "/v1/organizations/{organizationId}/volunteers/{membershipId}",
    operation_id="getVolunteerProfile",
    response_model=VolunteerProfileResponse,
)
async def get_volunteer_profile(
    organizationId: UUID,  # noqa: N803
    membershipId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> VolunteerProfileResponse:
    organization = await AuthenticationRepository(session).get_organization(organizationId)
    if organization is None:
        raise DomainError("organization_not_found", "找不到收容所", 404)
    result = await _service(session, organizationId).detail(
        membershipId,
        context=_context(context),
        as_of=local_today(organization.timezone),
    )
    membership = result.membership
    volunteer_no = membership.volunteer_no or "V---"
    label = f"{result.surname or '志工'}・{volunteer_no}"
    response = VolunteerProfileResponse(
        membership_id=membership.id,
        volunteer_no=volunteer_no,
        label=label,
        surname=result.surname,
        membership_status=membership.status,
        can_assist_new_volunteers=membership.can_assist_new_volunteers,
        statistics=VolunteerStatisticsResponse(**result.statistics.__dict__),
        notes=[_note_response(note, author) for note, author in result.notes],
        incidents=[VolunteerIncidentResponse.model_validate(item) for item in result.incidents],
        restrictions=[_restriction_response(item) for item in result.restrictions],
    )
    await session.commit()
    return response


@router.post(
    "/v1/organizations/{organizationId}/volunteers/{membershipId}/notes",
    response_model=VolunteerNoteResponse,
    operation_id="createVolunteerNote",
    status_code=201,
)
async def create_volunteer_note(
    organizationId: UUID,  # noqa: N803
    membershipId: UUID,  # noqa: N803
    payload: VolunteerNoteCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> VolunteerNoteResponse:
    note = await _service(session, organizationId).add_note(
        membershipId,
        content=payload.content,
        context=_context(context),
        author_membership_id=context.membership_id,
    )
    await session.commit()
    return _note_response(note, "你")


@router.patch(
    "/v1/organizations/{organizationId}/volunteers/{membershipId}/assist-flag",
    response_model=VolunteerAssistFlagRequest,
    operation_id="updateVolunteerAssistFlag",
)
async def update_volunteer_assist_flag(
    organizationId: UUID,  # noqa: N803
    membershipId: UUID,  # noqa: N803
    payload: VolunteerAssistFlagRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> VolunteerAssistFlagRequest:
    membership = await _service(session, organizationId).set_assist_flag(
        membershipId,
        value=payload.can_assist_new_volunteers,
        context=_context(context),
    )
    await session.commit()
    return VolunteerAssistFlagRequest(
        can_assist_new_volunteers=membership.can_assist_new_volunteers
    )


@router.post(
    "/v1/organizations/{organizationId}/volunteers/{membershipId}/incidents",
    response_model=VolunteerIncidentResponse,
    operation_id="createVolunteerIncident",
    status_code=201,
)
async def create_volunteer_incident(
    organizationId: UUID,  # noqa: N803
    membershipId: UUID,  # noqa: N803
    payload: VolunteerIncidentCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> VolunteerIncidentResponse:
    incident = await _service(session, organizationId).add_incident(
        membershipId,
        incident_type=payload.incident_type,
        severity=payload.severity,
        factual_summary=payload.factual_summary,
        occurred_at=payload.occurred_at,
        context=_context(context),
        author_membership_id=context.membership_id,
    )
    await session.commit()
    return VolunteerIncidentResponse.model_validate(incident)


@router.post(
    "/v1/organizations/{organizationId}/volunteer-incidents/{incidentId}/decision",
    response_model=VolunteerIncidentResponse,
    operation_id="decideVolunteerIncident",
)
async def decide_volunteer_incident(
    organizationId: UUID,  # noqa: N803
    incidentId: UUID,  # noqa: N803
    payload: VolunteerIncidentDecisionRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> VolunteerIncidentResponse:
    incident = await _service(session, organizationId).review_incident(
        incidentId,
        decision=payload.decision,
        context=_context(context),
    )
    await session.commit()
    return VolunteerIncidentResponse.model_validate(incident)


@router.post(
    "/v1/organizations/{organizationId}/volunteer-incidents/{incidentId}/restrictions",
    response_model=VolunteerRestrictionResponse,
    operation_id="createVolunteerRestriction",
    status_code=201,
)
async def create_volunteer_restriction(
    organizationId: UUID,  # noqa: N803
    incidentId: UUID,  # noqa: N803
    payload: VolunteerRestrictionCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> VolunteerRestrictionResponse:
    restriction = await _service(session, organizationId).request_restriction(
        incidentId,
        scope=payload.scope,
        reason_category=payload.reason_category,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        context=_context(context),
        requester_membership_id=context.membership_id,
    )
    await session.commit()
    return _restriction_response(restriction)


@router.get(
    "/v1/platform/volunteer-restrictions",
    response_model=list[PlatformRestrictionReviewItemResponse],
    operation_id="listPlatformVolunteerRestrictions",
)
async def list_platform_volunteer_restrictions(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> list[PlatformRestrictionReviewItemResponse]:
    placeholder_organization = UUID(int=0)
    rows = await _service(session, placeholder_organization).list_pending_platform_restrictions(
        context=_context(context)
    )
    response = [
        PlatformRestrictionReviewItemResponse(
            restriction=_restriction_response(restriction),
            incident=VolunteerIncidentResponse.model_validate(incident),
            originating_organization_id=restriction.organization_id,
            originating_organization_name=organization_name,
        )
        for restriction, incident, organization_name in rows
    ]
    await session.commit()
    return response


@router.post(
    "/v1/platform/volunteer-restrictions/{restrictionId}/decision",
    response_model=VolunteerRestrictionResponse,
    operation_id="decidePlatformVolunteerRestriction",
)
async def decide_platform_volunteer_restriction(
    restrictionId: UUID,  # noqa: N803
    payload: PlatformRestrictionDecisionRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> VolunteerRestrictionResponse:
    placeholder_organization = UUID(int=0)
    restriction = await _service(session, placeholder_organization).decide_platform_restriction(
        restrictionId,
        decision=payload.decision,
        reason=payload.reason,
        context=_context(context),
    )
    await session.commit()
    return _restriction_response(restriction)
