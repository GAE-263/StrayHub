from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.observation_option_service import ObservationOptionService
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Observation Vocabulary"])


class ObservationOptionResponse(BaseModel):
    id: UUID
    category_id: UUID
    code: str
    display_name: str
    description: str
    status: str
    display_order: int
    requires_note: bool


class ObservationOptionCreateRequest(BaseModel):
    category_id: UUID
    code: str
    display_name: str
    description: str = ""
    requires_note: bool = False


class ObservationOptionUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    display_order: int | None = None
    enabled: bool | None = None


@router.get("/v1/observation-options")
async def list_observation_options(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if context.organization_id is None:
        return {"items": []}
    options = await ObservationRepository(session, context.organization_id).effective_options(
        include_disabled_history=True
    )
    return {
        "items": [
            ObservationOptionResponse.model_validate(option, from_attributes=True)
            for option in options
        ]
    }


@router.get("/v1/observation-categories")
async def list_observation_categories(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if context.organization_id is None:
        return {"items": []}
    categories = await ObservationRepository(session, context.organization_id).categories()
    return {
        "items": [
            {
                "id": category.id,
                "organization_id": category.organization_id,
                "code": category.code,
                "display_name": category.display_name,
                "description": category.description,
                "status": category.status,
                "display_order": category.display_order,
            }
            for category in categories
        ]
    }


@router.post(
    "/v1/observation-options",
    response_model=ObservationOptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_observation_option(
    payload: ObservationOptionCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionResponse:
    if context.organization_id is None or context.role not in {
        "PLATFORM_ADMIN",
        "SHELTER_ADMIN",
        "STAFF",
    }:
        raise DomainError("option_management_denied", "無法管理觀察選項", 403)
    option = await ObservationOptionService(
        ObservationRepository(session, context.organization_id), audit=AuditService(session)
    ).create(**payload.model_dump(), actor_user_id=context.user_id)
    await session.commit()
    return ObservationOptionResponse.model_validate(option, from_attributes=True)


@router.patch("/v1/observation-options/{optionId}", response_model=ObservationOptionResponse)
async def update_observation_option(
    optionId: UUID,  # noqa: N803
    payload: ObservationOptionUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionResponse:
    if context.organization_id is None or context.role not in {
        "PLATFORM_ADMIN",
        "SHELTER_ADMIN",
        "STAFF",
    }:
        raise DomainError("option_management_denied", "無法管理觀察選項", 403)
    option = await ObservationOptionService(
        ObservationRepository(session, context.organization_id), audit=AuditService(session)
    ).update(
        optionId,
        **payload.model_dump(exclude_none=True),
        actor_user_id=context.user_id,
    )
    await session.commit()
    return ObservationOptionResponse.model_validate(option, from_attributes=True)
