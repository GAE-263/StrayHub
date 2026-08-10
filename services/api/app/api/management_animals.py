from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.management_animal_service import ManagementAnimalService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management/animals", tags=["Management Animals"])


@router.get("")
async def list_management_animals(
    query: str | None = Query(default=None),  # noqa: B008
    area_id: UUID | None = Query(default=None),  # noqa: B008
    status: str = Query(default="active"),  # noqa: B008
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=20, ge=1, le=100),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await ManagementAnimalService(session, organization_id).list(
        query=query,
        area_id=area_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/{animal_id}")
async def get_management_animal(
    animal_id: UUID,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await ManagementAnimalService(session, organization_id).get(animal_id)
