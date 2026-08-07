from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.ai_review import AIReviewService
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.repositories.ai_observation_repository import (
    AIObservationRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["AI Observations"])


class AIObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    source_type: str
    source_id: UUID | None
    status: str
    raw_ai_output: dict | list | str | None
    validated_ai_observation: dict | None
    human_review_result: dict | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None


class AIReviewRequest(BaseModel):
    action: str
    result: dict | None = None


@router.get("/v1/ai-observations/{observationId}", response_model=AIObservationResponse)
async def get_ai_observation(
    observationId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AIObservationResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    observation = await AIObservationRepository(session, context.organization_id).get(observationId)
    if observation is None:
        raise DomainError("observation_not_found", "AI Observation 不存在或無法存取", 404)
    return AIObservationResponse.model_validate(observation)


@router.get("/v1/care-reports/{reportId}/ai-observations")
async def list_ai_observations(
    reportId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict[str, list[AIObservationResponse]]:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    items = await AIObservationRepository(session, context.organization_id).list_for_source(
        reportId
    )
    return {"items": [AIObservationResponse.model_validate(item) for item in items]}


@router.post(
    "/v1/ai-observations/{observationId}/review",
    response_model=AIObservationResponse,
    status_code=status.HTTP_200_OK,
)
async def review_ai_observation(
    observationId: UUID,  # noqa: N803
    payload: AIReviewRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AIObservationResponse:
    if context.organization_id is None or context.role not in {
        "PLATFORM_ADMIN",
        "SHELTER_ADMIN",
        "STAFF",
    }:
        raise DomainError("ai_review_denied", "無法覆核 AI Observation", 403)
    if context.user_id is None:
        raise DomainError("authentication_required", "請先完成身分驗證", 401)
    repository = AIObservationRepository(session, context.organization_id)
    observation = await AIReviewService(repository, audit=AuditService(session)).review(
        observationId,
        actor_user_id=context.user_id,
        action=payload.action,
        result=payload.result,
    )
    await session.commit()
    return AIObservationResponse.model_validate(observation)
