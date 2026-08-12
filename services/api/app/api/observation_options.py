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
from services.api.app.api.management_access import (
    require_admin_context,
    require_staff_or_admin,
)
from services.api.app.application.audit_service import AuditService
from services.api.app.application.observation_option_service import ObservationOptionService
from services.api.app.application.observation_option_usage_service import (
    ObservationOptionUsageService,
)
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.observation import ObservationCategory, ObservationOption
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Observation Vocabulary"])
MANAGER_ROLES = {"PLATFORM_ADMIN", "SHELTER_ADMIN"}


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
    has_historical_usage: bool
    historical_usage_count: int
    last_modified_at: datetime
    last_modified_by: str | None
    updated_at: datetime


class ObservationAdminSummary(BaseModel):
    scope: str = "admin_full"
    category_count: int
    active_option_count: int
    custom_option_count: int
    inactive_option_count: int


class ObservationStaffSummary(BaseModel):
    scope: str = "staff_active"
    category_count: int
    active_option_count: int


class ObservationAdminCategoryCount(BaseModel):
    scope: str = "admin_full"
    category_id: UUID
    active_count: int
    custom_count: int
    inactive_count: int


class ObservationStaffCategoryCount(BaseModel):
    scope: str = "staff_active"
    category_id: UUID
    active_count: int


class ObservationOptionListResponse(BaseModel):
    items: list[ObservationOptionResponse]
    summary: ObservationAdminSummary | ObservationStaffSummary
    category_counts: list[ObservationAdminCategoryCount | ObservationStaffCategoryCount]


class ObservationOptionCreateRequest(BaseModel):
    category_id: UUID
    code: str = Field(..., min_length=1, max_length=120)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    display_order: int = Field(default=0, ge=0)
    requires_note: bool = False


class ObservationOptionUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    display_order: int | None = Field(default=None, ge=0)
    requires_note: bool | None = None
    enabled: bool | None = None
    expected_updated_at: datetime = Field(...)


class ObservationOptionReorderItem(BaseModel):
    option_id: UUID
    display_order: int = Field(..., ge=0)


class ObservationOptionReorderRequest(BaseModel):
    items: list[ObservationOptionReorderItem] = Field(..., min_length=1)


class ObservationLifecycleRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


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


def _require_manager(context: RequestContext) -> UUID:
    if context.role not in MANAGER_ROLES:
        raise DomainError("option_management_denied", "目前帳號無法管理觀察選項", 403)
    return require_admin_context(context)


def _require_option_manager(context: RequestContext) -> UUID:
    """Backward-compatible helper used by existing isolation checks."""
    return _require_manager(context)


async def _last_modifiers(
    session: AsyncSession, organization_id: UUID, option_ids: list[UUID]
) -> dict[UUID, UUID | None]:
    if not option_ids:
        return {}
    result = await session.execute(
        select(AuditRecord)
        .where(
            AuditRecord.organization_id == organization_id,
            AuditRecord.resource_type == "ObservationOption",
            AuditRecord.resource_id.in_(option_ids),
        )
        .order_by(AuditRecord.created_at.desc())
    )
    values: dict[UUID, UUID | None] = {}
    for record in result.scalars():
        if record.resource_id not in values:
            values[record.resource_id] = record.actor_user_id
    return values


async def _option_responses(
    session: AsyncSession,
    organization_id: UUID,
    options: list[ObservationOption],
    *,
    can_manage: bool,
) -> list[ObservationOptionResponse]:
    usage = ObservationOptionUsageService(session, organization_id)
    modifiers = await _last_modifiers(session, organization_id, [item.id for item in options])
    responses: list[ObservationOptionResponse] = []
    for option in options:
        count = await usage.count(option.id) if option.organization_id is not None else 0
        responses.append(
            ObservationOptionResponse(
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
                source="platform_default"
                if option.organization_id is None
                else "organization_extension",
                editable=bool(can_manage and option.organization_id is not None),
                has_historical_usage=count > 0,
                historical_usage_count=count,
                last_modified_at=option.updated_at,
                last_modified_by=(
                    str(modifiers[option.id]) if modifiers.get(option.id) else "系統"
                ),
                updated_at=option.updated_at,
            )
        )
    return responses


async def _list_payload(
    session: AsyncSession, context: RequestContext
) -> ObservationOptionListResponse:
    organization_id = require_staff_or_admin(context)
    repository = ObservationRepository(session, organization_id)
    categories = await repository.categories(include_disabled=True)
    all_options = await repository.effective_options(include_disabled_history=True)
    can_manage = context.role in MANAGER_ROLES
    options = (
        all_options if can_manage else [item for item in all_options if item.status == "active"]
    )
    responses = await _option_responses(session, organization_id, options, can_manage=can_manage)
    if can_manage:
        summary: ObservationAdminSummary | ObservationStaffSummary = ObservationAdminSummary(
            category_count=len(categories),
            active_option_count=sum(item.status == "active" for item in all_options),
            custom_option_count=sum(item.organization_id is not None for item in all_options),
            inactive_option_count=sum(
                item.organization_id is not None and item.status in {"disabled", "archived"}
                for item in all_options
            ),
        )
        category_counts = [
            ObservationAdminCategoryCount(
                category_id=category.id,
                active_count=sum(
                    item.category_id == category.id and item.status == "active"
                    for item in all_options
                ),
                custom_count=sum(
                    item.category_id == category.id and item.organization_id is not None
                    for item in all_options
                ),
                inactive_count=sum(
                    item.category_id == category.id
                    and item.organization_id is not None
                    and item.status in {"disabled", "archived"}
                    for item in all_options
                ),
            )
            for category in categories
        ]
    else:
        summary = ObservationStaffSummary(
            category_count=len(categories),
            active_option_count=len(options),
        )
        category_counts = [
            ObservationStaffCategoryCount(
                category_id=category.id,
                active_count=sum(
                    item.category_id == category.id and item.status == "active" for item in options
                ),
            )
            for category in categories
        ]
    return ObservationOptionListResponse(
        items=responses,
        summary=summary,
        category_counts=category_counts,
    )


@router.get("/v1/observation-categories", response_model=dict)
async def list_observation_categories(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    categories = await ObservationRepository(session, organization_id).categories(
        include_disabled=False
    )
    return {"items": [_category_response(category) for category in categories]}


@router.get("/v1/observation-options", response_model=ObservationOptionListResponse)
async def list_observation_options(
    search: str | None = Query(default=None),  # noqa: B008
    category: str | None = Query(default=None),  # noqa: B008
    state: str | None = Query(default=None),  # noqa: B008
    source: str | None = Query(default=None),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionListResponse:
    # The page normally loads once and filters locally. Query parameters remain
    # safe for future server-side filtering without accepting organization scope.
    organization_id = require_staff_or_admin(context)
    payload = await _list_payload(session, context)
    if not any((search, category, state, source)):
        return payload
    needle = search.casefold().strip() if search else None
    category_ids_by_code = {
        item.code: item.id
        for item in await ObservationRepository(session, organization_id).categories(
            include_disabled=True
        )
    }
    items = [
        item
        for item in payload.items
        if (
            not needle
            or needle in " ".join((item.code, item.display_name, item.description)).casefold()
        )
        and (not state or item.status == state)
        and (not category or item.category_id == category_ids_by_code.get(category))
        and (
            not source
            or (source == "platform_default" and item.source == "platform_default")
            or (source == "organization_extension" and item.source == "organization_extension")
        )
    ]
    return payload.model_copy(update={"items": items})


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
    organization_id = _require_manager(context)
    option = await ObservationOptionService(
        ObservationRepository(session, organization_id),
        audit=AuditService(session),
        usage=ObservationOptionUsageService(session, organization_id),
    ).create(**payload.model_dump(), actor_user_id=context.user_id)
    await session.commit()
    return (await _option_responses(session, organization_id, [option], can_manage=True))[0]


@router.post(
    "/v1/observation-options/reorder",
    response_model=ObservationOptionListResponse,
)
async def reorder_observation_options(
    payload: ObservationOptionReorderRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionListResponse:
    organization_id = _require_manager(context)
    service = ObservationOptionService(
        ObservationRepository(session, organization_id), audit=AuditService(session)
    )
    await service.reorder(
        [item.option_id for item in payload.items],
        display_orders={item.option_id: item.display_order for item in payload.items},
        actor_user_id=context.user_id,
    )
    await session.commit()
    return await _list_payload(session, context)


@router.patch("/v1/observation-options/{optionId}", response_model=ObservationOptionResponse)
async def update_observation_option(
    optionId: UUID,  # noqa: N803
    payload: ObservationOptionUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionResponse:
    organization_id = _require_manager(context)
    option = await ObservationOptionService(
        ObservationRepository(session, organization_id),
        audit=AuditService(session),
        usage=ObservationOptionUsageService(session, organization_id),
    ).update(
        optionId,
        **payload.model_dump(exclude_none=True),
        actor_user_id=context.user_id,
    )
    await session.commit()
    return (await _option_responses(session, organization_id, [option], can_manage=True))[0]


async def _lifecycle(
    option_id: UUID,
    *,
    action: str,
    context: RequestContext,
    session: AsyncSession,
    reason: str | None,
) -> ObservationOptionResponse:
    organization_id = _require_manager(context)
    service = ObservationOptionService(
        ObservationRepository(session, organization_id), audit=AuditService(session)
    )
    if action == "archive":
        option = await service.archive(option_id, actor_user_id=context.user_id, reason=reason)
    elif action == "disable":
        option = await service.disable(option_id, actor_user_id=context.user_id)
    else:
        option = await service.restore(option_id, actor_user_id=context.user_id)
    await session.commit()
    return (await _option_responses(session, organization_id, [option], can_manage=True))[0]


@router.post("/v1/observation-options/{optionId}/disable", response_model=ObservationOptionResponse)
async def disable_observation_option(
    optionId: UUID,
    payload: ObservationLifecycleRequest | None = None,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionResponse:
    return await _lifecycle(
        optionId,
        action="disable",
        context=context,
        session=session,
        reason=payload.reason if payload else None,
    )


@router.post("/v1/observation-options/{optionId}/restore", response_model=ObservationOptionResponse)
async def restore_observation_option(
    optionId: UUID,
    payload: ObservationLifecycleRequest | None = None,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionResponse:
    return await _lifecycle(
        optionId,
        action="restore",
        context=context,
        session=session,
        reason=payload.reason if payload else None,
    )


@router.post("/v1/observation-options/{optionId}/archive", response_model=ObservationOptionResponse)
async def archive_observation_option(
    optionId: UUID,
    payload: ObservationLifecycleRequest | None = None,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ObservationOptionResponse:
    return await _lifecycle(
        optionId,
        action="archive",
        context=context,
        session=session,
        reason=payload.reason if payload else None,
    )
