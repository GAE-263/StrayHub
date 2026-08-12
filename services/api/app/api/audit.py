from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.management_access import require_admin_context, require_staff_or_admin
from services.api.app.persistence.models.audit import AuditRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management/audit", tags=["Management Audit"])


def _payload(value: AuditRecord) -> dict:
    return {
        "id": str(value.id),
        "organization_id": str(value.organization_id) if value.organization_id else None,
        "actor_user_id": str(value.actor_user_id) if value.actor_user_id else None,
        "operation_id": str(value.operation_id),
        "action": value.action,
        "resource_type": value.resource_type,
        "resource_id": str(value.resource_id) if value.resource_id else None,
        "source_channel": value.source_channel,
        "before": value.before_data,
        "after": value.after_data,
        "reason": value.reason,
        "result": value.result,
        "created_at": value.created_at.isoformat(),
    }


@router.get("")
async def query_audit(
    actor_user_id: UUID | None = Query(default=None),  # noqa: B008
    resource_type: str | None = Query(default=None),  # noqa: B008
    resource_id: UUID | None = Query(default=None),  # noqa: B008
    action: str | None = Query(default=None),  # noqa: B008
    from_time: datetime | None = Query(default=None),  # noqa: B008
    to_time: datetime | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=100, ge=1, le=200),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if resource_type == "ObservationOption":
        organization_id = require_admin_context(context)
    else:
        organization_id = require_staff_or_admin(context)
    query = select(AuditRecord).where(AuditRecord.organization_id == organization_id)
    if actor_user_id:
        query = query.where(AuditRecord.actor_user_id == actor_user_id)
    if resource_type:
        query = query.where(AuditRecord.resource_type == resource_type)
    if resource_id:
        query = query.where(AuditRecord.resource_id == resource_id)
    if action:
        query = query.where(AuditRecord.action == action)
    if from_time:
        query = query.where(AuditRecord.created_at >= from_time)
    if to_time:
        query = query.where(AuditRecord.created_at <= to_time)
    result = await session.execute(query.order_by(AuditRecord.created_at.desc()).limit(limit))
    return {"items": [_payload(item) for item in result.scalars()]}
