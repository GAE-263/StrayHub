from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.line_draft_service import LineDraftService
from services.api.app.config.settings import get_settings
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/line/care-report/drafts", tags=["LINE Bot"])


class DraftResumeResponse(BaseModel):
    id: UUID
    organization_id: UUID
    animal_id: UUID
    current_step: str
    answers: dict
    status: str
    expires_at: datetime


def _response(draft) -> DraftResumeResponse:
    return DraftResumeResponse(
        id=draft.id,
        organization_id=draft.organization_id,
        animal_id=draft.animal_id,
        current_step=draft.current_step,
        answers=draft.answers,
        status=draft.status,
        expires_at=draft.expires_at,
    )


@router.get("/current", response_model=DraftResumeResponse | None)
async def current_draft(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> DraftResumeResponse | None:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    draft = await CareReportDraftRepository(
        session, context.organization_id
    ).get_active_for_volunteer(context.user_id)
    return _response(draft) if draft is not None else None


@router.post("/{draftId}/resume", response_model=DraftResumeResponse)
async def resume_draft(
    draftId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> DraftResumeResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    draft = await CareReportDraftRepository(session, context.organization_id).get(draftId)
    if draft is None or draft.volunteer_user_id != context.user_id or draft.status != "active":
        raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
    if draft.expires_at <= datetime.now(timezone.utc):
        await LineDraftService(
            CareReportDraftRepository(session, context.organization_id),
            ttl_seconds=get_settings().draft_ttl_seconds,
        ).expire(draft.id)
        raise DomainError("draft_expired", "草稿已過期", 409)
    return _response(draft)


@router.post("/{draftId}/cancel", status_code=204)
async def cancel_draft(
    draftId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> Response:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    draft_repository = CareReportDraftRepository(session, context.organization_id)
    draft = await draft_repository.get(draftId)
    if draft is None or draft.volunteer_user_id != context.user_id:
        raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
    await LineDraftService(
        draft_repository,
        ttl_seconds=get_settings().draft_ttl_seconds,
    ).cancel(draft.id)
    await session.commit()
    return Response(status_code=204)
