from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.care_report_handoff_service import (
    CareReportHandoffService,
)
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.care_report_handoff_repository import (
    CareReportHandoffRepository,
)
from services.api.app.persistence.repositories.reportable_scope_repository import (
    ReportableScopeRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/care-report-handoffs", tags=["Care Report Handoffs"])


class CareReportHandoffCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    animal_id: UUID
    confirmation_token: str = Field(min_length=1)
    source: Literal["liff_scan", "qr_deeplink", "shelter_number"]


class CareReportHandoffResponse(BaseModel):
    id: UUID
    status: Literal["pending"]
    expires_at: datetime


@router.post(
    "",
    response_model=CareReportHandoffResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_replace_care_report_handoff(
    payload: CareReportHandoffCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> CareReportHandoffResponse:
    if (
        context.role != "VOLUNTEER"
        or context.organization_id is None
        or context.membership_id is None
    ):
        raise DomainError("volunteer_access_required", "需要有效志工權限", 403)
    if context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)

    organization_id = context.organization_id
    handoff = await CareReportHandoffService(
        CareReportHandoffRepository(session, organization_id),
        authentication=AuthenticationRepository(session),
        animals=AnimalRepository(session, organization_id),
        reportable_scopes=ReportableScopeRepository(session, organization_id),
    ).create_or_replace_handoff(
        user_id=context.user_id,
        organization_id=organization_id,
        membership_id=context.membership_id,
        session_id=context.session_id,
        animal_id=payload.animal_id,
        confirmation_token=payload.confirmation_token,
        source=payload.source,
    )
    await session.commit()
    return CareReportHandoffResponse(
        id=handoff.id,
        status=handoff.status,
        expires_at=handoff.expires_at,
    )
