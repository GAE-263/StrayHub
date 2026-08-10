from __future__ import annotations

from fastapi import APIRouter, Depends
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.dashboard_service import DashboardService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management", tags=["Management Workbench"])


@router.get("/dashboard")
async def dashboard_summary(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await DashboardService(session).summary(
        organization_id=organization_id,
        role=context.role,
    )
