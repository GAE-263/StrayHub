from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.adoption_inquiry_service import AdoptionInquiryInboxService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/v1/management/adoption-inquiries", tags=["Management Adoption Inquiries"]
)


class StatusUpdateRequest(BaseModel):
    status: str


@router.get("")
async def list_adoption_inquiries(
    search: str | None = Query(default=None),  # noqa: B008
    path: str | None = Query(default=None),  # noqa: B008
    inquiry_status: str | None = Query(default=None, alias="status"),  # noqa: B008
    from_date: date | None = Query(default=None),  # noqa: B008
    to_date: date | None = Query(default=None),  # noqa: B008
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=20, ge=1, le=100),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await AdoptionInquiryInboxService(session, organization_id).list(
        search=search,
        path=path,
        inquiry_status=inquiry_status,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )


@router.patch("/{inquiry_id}/status")
async def update_adoption_inquiry_status(
    inquiry_id: UUID,
    payload: StatusUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    inquiry = await AdoptionInquiryInboxService(session, organization_id).set_status(
        inquiry_id, inquiry_status=payload.status, actor_user_id=context.user_id
    )
    await session.commit()
    return {"inquiry": inquiry}
