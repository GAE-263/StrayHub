from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import require_admin_context, require_staff_or_admin
from services.api.app.application.audit_service import AuditService
from services.api.app.application.reportable_scope_service import ReportableScopeService
from services.api.app.persistence.models.reportable_scope import DailyReportableScope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management/reportable-scopes", tags=["Management Settings"])


class ScopeCreateRequest(BaseModel):
    animal_id: UUID | None = None
    area_id: UUID | None = None
    volunteer_user_id: UUID | None = None
    starts_at: datetime
    ends_at: datetime


class ScopeUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|inactive)$")
    ends_at: datetime | None = None


def _scope_payload(scope: DailyReportableScope) -> dict:
    return {
        "id": str(scope.id),
        "organization_id": str(scope.organization_id),
        "animal_id": str(scope.animal_id) if scope.animal_id else None,
        "area_id": str(scope.area_id) if scope.area_id else None,
        "volunteer_user_id": str(scope.volunteer_user_id) if scope.volunteer_user_id else None,
        "starts_at": scope.starts_at.isoformat(),
        "ends_at": scope.ends_at.isoformat(),
        "status": scope.status,
    }


@router.get("")
async def list_scopes(
    include_inactive: bool = Query(default=False),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    query = select(DailyReportableScope).where(
        DailyReportableScope.organization_id == organization_id
    )
    if not include_inactive:
        query = query.where(DailyReportableScope.status == "active")
    result = await session.execute(query.order_by(DailyReportableScope.starts_at.desc()))
    return {"items": [_scope_payload(item) for item in result.scalars()]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_scope(
    payload: ScopeCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_admin_context(context)
    await ReportableScopeService(session).validate_target(
        organization_id=organization_id,
        animal_id=payload.animal_id,
        area_id=payload.area_id,
        volunteer_user_id=payload.volunteer_user_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    scope = DailyReportableScope(
        organization_id=organization_id,
        animal_id=payload.animal_id,
        area_id=payload.area_id,
        volunteer_user_id=payload.volunteer_user_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status="active",
    )
    session.add(scope)
    await session.flush()
    await AuditService(session).record(
        organization_id=organization_id,
        actor_user_id=context.user_id,
        action="reportable_scope.created",
        resource_type="DailyReportableScope",
        resource_id=scope.id,
        source_channel="api",
        after=_scope_payload(scope),
    )
    await session.commit()
    return _scope_payload(scope)


@router.patch("/{scope_id}")
async def update_scope(
    scope_id: UUID,
    payload: ScopeUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_admin_context(context)
    scope = await session.scalar(
        select(DailyReportableScope).where(
            DailyReportableScope.id == scope_id,
            DailyReportableScope.organization_id == organization_id,
        )
    )
    if scope is None:
        raise DomainError("scope_not_found", "可回報範圍不存在或無法存取", 404)
    before = _scope_payload(scope)
    if payload.status is not None:
        scope.status = payload.status
    if payload.ends_at is not None:
        await ReportableScopeService(session).validate_target(
            organization_id=organization_id,
            animal_id=scope.animal_id,
            area_id=scope.area_id,
            volunteer_user_id=scope.volunteer_user_id,
            starts_at=scope.starts_at,
            ends_at=payload.ends_at,
        )
        scope.ends_at = payload.ends_at
    await session.flush()
    await AuditService(session).record(
        organization_id=organization_id,
        actor_user_id=context.user_id,
        action="reportable_scope.updated",
        resource_type="DailyReportableScope",
        resource_id=scope.id,
        source_channel="api",
        before=before,
        after=_scope_payload(scope),
    )
    await session.commit()
    return _scope_payload(scope)
