from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import ErrorResponse
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.adoption_inquiry_service import AdoptionInquiryInboxService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/v1/management/adoption-inquiries", tags=["Management Adoption Inquiries"]
)
ERROR_RESPONSES = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422)}


class StatusUpdateRequest(BaseModel):
    status: Literal["new", "contacted"]


class AdoptionAnswerDisplay(BaseModel):
    key: str
    label: str
    value: str


class AdoptionInquiryItem(BaseModel):
    id: UUID
    organization_id: UUID
    target_animal_id: UUID
    animal_name: str
    shelter_number: str | None
    path: Literal["specific_animal", "recommend_me"]
    adopter_name: str
    phone_number: str
    answers: dict[str, str]
    answers_display: list[AdoptionAnswerDisplay]
    status: Literal["new", "contacted"]
    staff_notes: str | None
    submitted_at: datetime
    status_updated_at: datetime | None
    ai_suitability_score: int | None
    ai_suitability_explanation: str | None
    ai_recommendation_overridden: bool | None


class AdoptionInquiryListResponse(BaseModel):
    items: list[AdoptionInquiryItem]
    page: int
    page_size: int
    total: int


class AdoptionInquiryStatusResponse(BaseModel):
    inquiry: AdoptionInquiryItem


@router.get("", response_model=AdoptionInquiryListResponse, responses=ERROR_RESPONSES)
async def list_adoption_inquiries(
    search: str | None = Query(default=None, max_length=120),  # noqa: B008
    path: Literal["specific_animal", "recommend_me"] | None = Query(default=None),  # noqa: B008
    inquiry_status: Literal["new", "contacted"] | None = Query(  # noqa: B008
        default=None, alias="status"
    ),
    from_date: date | None = Query(default=None),  # noqa: B008
    to_date: date | None = Query(default=None),  # noqa: B008
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=20, ge=1, le=100),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AdoptionInquiryListResponse:
    organization_id = require_staff_or_admin(context)
    result = await AdoptionInquiryInboxService(session, organization_id).list(
        search=search,
        path=path,
        inquiry_status=inquiry_status,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    return AdoptionInquiryListResponse.model_validate(result)


@router.patch(
    "/{inquiry_id}/status",
    response_model=AdoptionInquiryStatusResponse,
    responses=ERROR_RESPONSES,
)
async def update_adoption_inquiry_status(
    inquiry_id: UUID,
    payload: StatusUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AdoptionInquiryStatusResponse:
    organization_id = require_staff_or_admin(context)
    inquiry = await AdoptionInquiryInboxService(session, organization_id).set_status(
        inquiry_id, inquiry_status=payload.status, actor_user_id=context.user_id
    )
    await session.commit()
    return AdoptionInquiryStatusResponse.model_validate({"inquiry": inquiry})
