from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.ai_review import AIReviewService
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.repositories.ai_observation_repository import (
    AIObservationRepository,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["AI Observations"])


class AIObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    source_type: str
    source_id: UUID | None
    animal_name: str | None
    shelter_number: str | None
    report_submitted_at: datetime | None
    status: str
    provider: str
    model_name: str
    model_version: str
    prompt_template_id: str
    prompt_version: str
    output_schema_version: str
    raw_ai_output: dict | list | str | None
    validation_result: dict | None
    failure_reason: str | None
    validated_ai_observation: dict | None
    human_review_result: dict | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None


class AIReviewRequest(BaseModel):
    action: str = Field(pattern="^(confirm|reject|correct)$")
    reason: str = Field(min_length=1, max_length=500)
    corrected_observation: dict | None = None


def _response(observation, report: CareReport | None = None) -> AIObservationResponse:
    job = observation.job
    return AIObservationResponse(
        id=observation.id,
        job_id=observation.job_id,
        source_type=observation.source_type,
        source_id=observation.source_id,
        animal_name=report.animal_name_snapshot if report else None,
        shelter_number=report.shelter_number_snapshot if report else None,
        report_submitted_at=report.submitted_at if report else None,
        status=observation.status,
        provider=job.provider,
        model_name=job.model_name,
        model_version=job.model_version,
        prompt_template_id=job.prompt_template_id,
        prompt_version=job.prompt_version,
        output_schema_version=job.output_schema_version,
        raw_ai_output=observation.raw_ai_output,
        validation_result=job.validation_result,
        failure_reason=job.failure_reason,
        validated_ai_observation=observation.validated_ai_observation,
        human_review_result=observation.human_review_result,
        reviewed_by=observation.reviewed_by,
        reviewed_at=observation.reviewed_at,
    )


MANAGEMENT_ROLES = {"PLATFORM_ADMIN", "SHELTER_ADMIN", "STAFF"}


@router.get("/v1/management/ai-review")
async def list_management_ai_review_queue(
    observation_status: str | None = Query(default=None, alias="status"),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=100),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict[str, list[AIObservationResponse]]:
    organization_id = require_staff_or_admin(context)
    items = await AIObservationRepository(session, organization_id).list_for_review(
        status=observation_status,
        limit=limit,
    )
    report_ids = {
        item.source_id
        for item in items
        if item.source_type == "care_report_summary" and item.source_id is not None
    }
    reports_by_id: dict[UUID, CareReport] = {}
    if report_ids:
        result = await session.execute(
            select(CareReport).where(
                CareReport.organization_id == organization_id,
                CareReport.id.in_(report_ids),
            )
        )
        reports_by_id = {report.id: report for report in result.scalars()}
    return {
        "items": [
            _response(item, reports_by_id.get(item.source_id))
            for item in items
        ]
    }


@router.get("/v1/ai-observations/{observationId}", response_model=AIObservationResponse)
async def get_ai_observation(
    observationId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AIObservationResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    if context.role not in MANAGEMENT_ROLES:
        raise DomainError("ai_observation_denied", "無法查看 AI Observation", 403)
    observation = await AIObservationRepository(session, context.organization_id).get(observationId)
    if observation is None:
        raise DomainError("observation_not_found", "AI Observation 不存在或無法存取", 404)
    return _response(observation)


@router.get("/v1/care-reports/{reportId}/ai-observations")
async def list_ai_observations(
    reportId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict[str, list[AIObservationResponse]]:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    if context.role not in MANAGEMENT_ROLES:
        raise DomainError("ai_observation_denied", "無法查看 AI Observation", 403)
    items = await AIObservationRepository(session, context.organization_id).list_for_report(
        reportId
    )
    return {"items": [_response(item) for item in items]}


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
        result=payload.corrected_observation,
        reason=payload.reason,
    )
    await session.commit()
    return _response(observation)


@router.post(
    "/v1/management/ai-review/{observationId}/review",
    response_model=AIObservationResponse,
    status_code=status.HTTP_200_OK,
)
async def review_management_ai_observation(
    observationId: UUID,  # noqa: N803
    payload: AIReviewRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AIObservationResponse:
    organization_id = require_staff_or_admin(context)
    if context.user_id is None:
        raise DomainError("authentication_required", "請先完成身分驗證", 401)
    repository = AIObservationRepository(session, organization_id)
    observation = await AIReviewService(repository, audit=AuditService(session)).review(
        observationId,
        actor_user_id=context.user_id,
        action=payload.action,
        result=payload.corrected_observation,
        reason=payload.reason,
    )
    await session.commit()
    return _response(observation)
