from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.adoption_inbox_service import AdoptionInboxService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/v1/management/adoption-inquiries", tags=["Management Adoption Inquiries"]
)


class AdoptionInquiryStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=30)
    staff_notes: str | None = Field(default=None, max_length=2000)


@router.get("")
async def list_adoption_inquiries(
    from_date: date | None = Query(default=None),  # noqa: B008
    to_date: date | None = Query(default=None),  # noqa: B008
    animal_id: UUID | None = Query(default=None),  # noqa: B008
    inquiry_status: str | None = Query(default=None, alias="status"),  # noqa: B008
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=20, ge=1, le=100),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await AdoptionInboxService(session, organization_id).list(
        from_date=from_date,
        to_date=to_date,
        animal_id=animal_id,
        inquiry_status=inquiry_status,
        page=page,
        page_size=page_size,
    )


@router.get("/{inquiry_id}")
async def get_adoption_inquiry_detail(
    inquiry_id: UUID,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return {"inquiry": await AdoptionInboxService(session, organization_id).detail(inquiry_id)}


@router.patch("/{inquiry_id}/status")
async def update_adoption_inquiry_status(
    inquiry_id: UUID,
    payload: AdoptionInquiryStatusUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return {
        "inquiry": await AdoptionInboxService(session, organization_id).update_status(
            inquiry_id,
            status=payload.status,
            staff_notes=payload.staff_notes,
            actor_user_id=context.user_id,
        )
    }
