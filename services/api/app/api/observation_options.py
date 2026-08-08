from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.observation_option_service import ObservationOptionService
from services.api.app.persistence.models.observation import ObservationCategory, ObservationOption
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Observation Vocabulary"])
OPTION_MANAGER_ROLES = {"PLATFORM_ADMIN", "SHELTER_ADMIN", "STAFF"}


class ObservationCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID | None
    code: str
    display_name: str
    description: str
    status: str
    display_order: int
    source: str


class ObservationOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    organization_id: UUID | None
    code: str
    display_name: str
    description: str
    status: str
    enabled: bool
    display_order: int
    requires_note: bool
    source: str
    editable: bool


class ObservationCategoryListResponse(BaseModel):
    items: list[ObservationCategoryResponse]


class ObservationOptionListResponse(BaseModel):
    items: list[ObservationOptionResponse]


class ObservationOptionCreateRequest(BaseModel):
    category_id: UUID
    code: str = Field(..., min_length=1, max_length=120)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    display_order: int = Field(default=0, ge=0)
    requires_note: bool = False


class ObservationOptionUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    display_order: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class ObservationOptionReorderItem(BaseModel):
    option_id: UUID
    display_order: int = Field(..., ge=0)


class ObservationOptionReorderRequest(BaseModel):
    items: list[ObservationOptionReorderItem] = Field(..., min_length=1)


def _require_option_manager(context: RequestContext) -> None:
    if context.organization_id is None or context.role not in OPTION_MANAGER_ROLES:
        raise DomainError("option_management_denied", "無法管理觀察選項", 403)


def _category_response(category: ObservationCategory) -> ObservationCategoryResponse:
    return ObservationCategoryResponse(
        id=category.id,
        organization_id=category.organization_id,
        code=category.code,
        display_name=category.display_name,
        description=category.description,
        status=category.status,
        display_order=category.display_order,
        source="platform_default" if category.organization_id is None else "organization_extension",
    )


def _option_response(option: ObservationOption) -> ObservationOptionResponse:
    return ObservationOptionResponse(
        id=option.id,
        category_id=option.category_id,
        organization_id=option.organization_id,
        code=option.code,
        display_name=option.display_name,
        description=option.description,
        status=option.status,
        enabled=option.status == "active",
        display_order=option.display_order,
        requires_note=option.requires_note,
        source="platform_default" if option.organization_id is None else "organization_extension",
        editable=option.organization_id is not None,
    )


@router.get("/v1/observation-categories", response_model=ObservationCategoryListResponse)
async def list_observation_categories(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if context.organization_id is None:
        return {"items": []}
    categories = await ObservationRepository(session, context.organization_id).categories(
        include_disabled=True
    )
    return {"items": [_category_response(category) for category in categories]}


@router.get("/v1/observation-options", response_model=ObservationOptionListResponse)
async def list_observation_options(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if context.organization_id is None:
        return {"items": []}
    options = await ObservationRepository(session, context.organization_id).effective_options(
        include_disabled_history=True
    )
    return {"items": [_option_response(option) for option in options]}


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
    _require_option_manager(context)
    option = await ObservationOptionService(
        ObservationRepository(session, context.organization_id), audit=AuditService(session)
    ).create(**payload.model_dump(), actor_user_id=context.user_id)
    await session.commit()
    return _option_response(option)


@router.post(
    "/v1/observation-options/reorder",
    response_model=ObservationOptionListResponse,
)
async def reorder_observation_options(
    payload: ObservationOptionReorderRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    _require_option_manager(context)
    options = await ObservationOptionService(
        ObservationRepository(session, context.organization_id), audit=AuditService(session)
    ).reorder([item.option_id for item in payload.items], actor_user_id=context.user_id)
    await session.commit()
    return {"items": [_option_response(option) for option in options]}


@router.patch("/v1/observation-options/{optionId}", response_model=ObservationOptionResponse)
async def update_observation_option(
    optionId: UUID,  # noqa: N803
    payload: ObservationOptionUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionResponse:
    _require_option_manager(context)
    option = await ObservationOptionService(
        ObservationRepository(session, context.organization_id), audit=AuditService(session)
    ).update(
        optionId,
        **payload.model_dump(exclude_none=True),
        actor_user_id=context.user_id,
    )
    await session.commit()
    return _option_response(option)
