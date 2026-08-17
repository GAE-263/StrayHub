from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.organization_management import OrganizationManagementService
from services.api.app.domain.organization_timezone import validate_timezone
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import Organization, OrganizationMembership
from services.api.app.persistence.models.shelter_area import ShelterArea
from services.api.app.persistence.repositories.organization_repository import OrganizationRepository
from services.api.app.persistence.repositories.shelter_area_repository import ShelterAreaRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Organizations"])


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    status: str
    address: str | None
    service_area: str | None
    contact: str | None
    timezone: str = "Asia/Taipei"
    timezone_version: int = 1


class OrganizationCreateRequest(BaseModel):
    code: str
    name: str
    status: Literal["pending_setup"] = Field(...)
    initial_admin_username: str = Field(..., min_length=1)
    initial_admin_temporary_password: str = Field(..., min_length=1)
    address: str | None = None
    service_area: str | None = None
    contact: str | None = None


class OrganizationUpdateRequest(BaseModel):
    name: str | None = None
    address: str | None = None
    service_area: str | None = None
    contact: str | None = None
    status: Literal["pending_setup", "active", "suspended"] | None = None
    timezone: str | None = None


class InitialAdminCreateRequest(BaseModel):
    username: str
    temporary_password: str


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
    status: str
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    access_version: int = 1
    medical_care_access: bool = False


class MembershipCreateRequest(BaseModel):
    user_id: UUID
    role: str


class MembershipUpdateRequest(BaseModel):
    role: str | None = None
    status: str | None = None
    medical_care_access: bool | None = None


class AccountCreateRequest(BaseModel):
    username: str
    display_name: str
    temporary_password: str
    role: Literal["SHELTER_ADMIN", "STAFF", "VOLUNTEER"]


class ShelterAreaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    area_type: str
    parent_id: UUID | None
    status: str


class ShelterAreaCreateRequest(BaseModel):
    name: str
    area_type: str = "area"
    parent_id: UUID | None = None


class ShelterAreaUpdateRequest(BaseModel):
    name: str | None = None
    area_type: str | None = None
    parent_id: UUID | None = None
    status: str | None = None


def _require_platform(context: RequestContext) -> None:
    if context.role != "PLATFORM_ADMIN" and not context.platform_scope:
        raise DomainError("platform_admin_required", "需要平台管理員權限", 403)


def _response(organization: Organization) -> OrganizationResponse:
    data = OrganizationResponse.model_validate(
        {
            "id": organization.id,
            "code": organization.code,
            "name": organization.name,
            "status": organization.status,
            "address": organization.address,
            "service_area": organization.service_area,
            "contact": organization.contact,
            "timezone": getattr(organization, "timezone", None) or "Asia/Taipei",
            "timezone_version": getattr(organization, "timezone_version", None) or 1,
        }
    )
    return data


def _membership_response(membership: OrganizationMembership) -> MembershipResponse:
    return MembershipResponse.model_validate(
        {
            "id": membership.id,
            "organization_id": membership.organization_id,
            "user_id": membership.user_id,
            "role": membership.role,
            "status": membership.status,
            "valid_from": membership.valid_from,
            "expires_at": membership.expires_at,
            "access_version": getattr(membership, "access_version", None) or 1,
            "medical_care_access": getattr(membership, "medical_care_access", False) or False,
        }
    )


def _area_response(area: ShelterArea) -> ShelterAreaResponse:
    return ShelterAreaResponse.model_validate(area, from_attributes=True)


def _require_active_organization(organization: Organization | None) -> Organization:
    if organization is None:
        raise DomainError("organization_not_found", "收容所不存在", 404)
    if organization.status != "active":
        raise DomainError("organization_not_active", "收容所尚未啟用或已停用", 409)
    return organization


def _require_membership_admin(context: RequestContext, organization_id: UUID) -> None:
    if context.platform_scope or context.role == "PLATFORM_ADMIN":
        return
    if context.organization_id != organization_id or context.role != "SHELTER_ADMIN":
        raise DomainError("membership_management_denied", "無法管理此收容所 Membership", 403)


@router.get("/v1/organizations")
async def list_organizations(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    repository = OrganizationRepository(session)
    if context.role == "PLATFORM_ADMIN" or context.platform_scope:
        organizations = await repository.list()
    elif context.organization_id is not None:
        organization = await repository.get(context.organization_id)
        organizations = [organization] if organization is not None else []
    else:
        organizations = []
    return {"items": [_response(value) for value in organizations]}


@router.post(
    "/v1/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    payload: OrganizationCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> OrganizationResponse:
    _require_platform(context)
    repository = OrganizationRepository(session)
    service = OrganizationManagementService(repository, Argon2PasswordHasher())
    organization = await service.create(
        code=payload.code,
        name=payload.name,
    )
    organization.address = payload.address
    organization.service_area = payload.service_area
    organization.contact = payload.contact
    initial_admin = await service.create_initial_admin(
        organization_id=organization.id,
        username=payload.initial_admin_username,
        temporary_password=payload.initial_admin_temporary_password,
    )
    membership = await repository.membership(initial_admin.id, organization.id)
    if membership is None:
        raise DomainError("membership_not_created", "初始管理員 Membership 建立失敗", 500)
    await AuditService(session).record(
        organization_id=organization.id,
        actor_user_id=context.user_id,
        action="organization.created",
        resource_type="organization",
        resource_id=organization.id,
        source_channel="api",
        after={"code": organization.code, "name": organization.name},
    )
    await AuditService(session).record(
        organization_id=organization.id,
        actor_user_id=context.user_id,
        action="membership.created",
        resource_type="organization_membership",
        resource_id=membership.id,
        source_channel="api",
        after={"user_id": initial_admin.id, "role": membership.role},
    )
    await session.commit()
    return _response(organization)


@router.get("/v1/organizations/{organizationId}", response_model=OrganizationResponse)
async def get_organization(
    organizationId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> OrganizationResponse:
    if (
        context.role != "PLATFORM_ADMIN"
        and not context.platform_scope
        and context.organization_id != organizationId
    ):
        raise DomainError("organization_access_denied", "無法存取此收容所資料", 404)
    organization = await OrganizationRepository(session).get(organizationId)
    if organization is None:
        raise DomainError("organization_not_found", "收容所不存在", 404)
    return _response(organization)


@router.patch("/v1/organizations/{organizationId}", response_model=OrganizationResponse)
async def update_organization(
    organizationId: UUID,  # noqa: N803
    payload: OrganizationUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> OrganizationResponse:
    _require_platform(context)
    organization = await OrganizationRepository(session).get(organizationId)
    if organization is None:
        raise DomainError("organization_not_found", "收容所不存在", 404)
    for field in ("name", "address", "service_area", "contact", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(organization, field, value)
    if payload.timezone is not None:
        organization.timezone = validate_timezone(payload.timezone)
        organization.timezone_version += 1
    await AuditService(session).record(
        organization_id=organization.id,
        actor_user_id=context.user_id,
        action="organization.updated",
        resource_type="organization",
        resource_id=organization.id,
        source_channel="api",
        after=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    return _response(organization)


@router.post("/v1/organizations/{organizationId}/disable", status_code=204)
async def disable_organization(
    organizationId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> Response:
    _require_platform(context)
    await OrganizationManagementService(
        OrganizationRepository(session), Argon2PasswordHasher()
    ).disable(organizationId)
    await AuditService(session).record(
        organization_id=organizationId,
        actor_user_id=context.user_id,
        action="organization.disabled",
        resource_type="organization",
        resource_id=organizationId,
        source_channel="api",
    )
    await session.commit()
    return Response(status_code=204)


@router.post("/v1/organizations/{organizationId}/initial-admin", status_code=201)
async def create_initial_admin(
    organizationId: UUID,  # noqa: N803
    payload: InitialAdminCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    _require_platform(context)
    user = await OrganizationManagementService(
        OrganizationRepository(session), Argon2PasswordHasher()
    ).create_initial_admin(
        organization_id=organizationId,
        username=payload.username,
        temporary_password=payload.temporary_password,
    )
    membership = await OrganizationRepository(session).membership(user.id, organizationId)
    if membership is None:
        raise DomainError("membership_not_created", "初始管理員 Membership 建立失敗", 500)
    await AuditService(session).record(
        organization_id=organizationId,
        actor_user_id=context.user_id,
        action="membership.created",
        resource_type="organization_membership",
        resource_id=membership.id,
        source_channel="api",
        after={"user_id": user.id, "role": membership.role},
    )
    await session.commit()
    return _membership_response(membership)


@router.get(
    "/v1/organizations/{organizationId}/memberships",
    response_model=dict,
)
async def list_memberships(
    organizationId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    _require_membership_admin(context, organizationId)
    memberships = await OrganizationRepository(session).memberships(organizationId)
    return {"items": [_membership_response(value) for value in memberships]}


@router.post(
    "/v1/organizations/{organizationId}/memberships",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_membership(
    organizationId: UUID,  # noqa: N803
    payload: MembershipCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MembershipResponse:
    _require_membership_admin(context, organizationId)
    membership = await OrganizationManagementService(
        OrganizationRepository(session), Argon2PasswordHasher()
    ).create_membership(
        organization_id=organizationId,
        user_id=payload.user_id,
        role=payload.role,
    )
    await AuditService(session).record(
        organization_id=organizationId,
        actor_user_id=context.user_id,
        action="membership.created",
        resource_type="organization_membership",
        resource_id=membership.id,
        source_channel="api",
        after={"user_id": membership.user_id, "role": membership.role},
    )
    await session.commit()
    return _membership_response(membership)


@router.post(
    "/v1/organizations/{organizationId}/accounts",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_account(
    organizationId: UUID,  # noqa: N803
    payload: AccountCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MembershipResponse:
    _require_membership_admin(context, organizationId)
    service = OrganizationManagementService(OrganizationRepository(session), Argon2PasswordHasher())
    user, membership = await service.create_account(
        organization_id=organizationId,
        username=payload.username,
        display_name=payload.display_name,
        temporary_password=payload.temporary_password,
        role=payload.role,
    )
    await AuditService(session).record(
        organization_id=organizationId,
        actor_user_id=context.user_id,
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        source_channel="api",
        after={"username": user.username, "display_name": user.display_name},
    )
    await AuditService(session).record(
        organization_id=organizationId,
        actor_user_id=context.user_id,
        action="membership.created",
        resource_type="organization_membership",
        resource_id=membership.id,
        source_channel="api",
        after={"user_id": user.id, "role": membership.role},
    )
    await session.commit()
    return _membership_response(membership)


@router.patch(
    "/v1/organizations/{organizationId}/memberships/{membershipId}",
    response_model=MembershipResponse,
)
async def update_membership(
    organizationId: UUID,  # noqa: N803
    membershipId: UUID,  # noqa: N803
    payload: MembershipUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MembershipResponse:
    _require_membership_admin(context, organizationId)
    repository = OrganizationRepository(session)
    membership = await repository.membership_by_id(membershipId, organizationId)
    if membership is None:
        raise DomainError("membership_not_found", "Membership 不存在或無法存取", 404)
    membership = await OrganizationManagementService(
        repository, Argon2PasswordHasher()
    ).update_membership(
        membership,
        role=payload.role,
        status=payload.status,
        medical_care_access=payload.medical_care_access,
    )
    await AuditService(session).record(
        organization_id=organizationId,
        actor_user_id=context.user_id,
        action="membership.updated",
        resource_type="organization_membership",
        resource_id=membership.id,
        source_channel="api",
        after=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    return _membership_response(membership)


@router.get("/v1/organizations/{organizationId}/areas", response_model=dict)
async def list_shelter_areas(
    organizationId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    _require_membership_admin(context, organizationId)
    _require_active_organization(await OrganizationRepository(session).get(organizationId))
    areas = await ShelterAreaRepository(session, organizationId).list()
    return {"items": [_area_response(area) for area in areas]}


@router.post(
    "/v1/organizations/{organizationId}/areas",
    response_model=ShelterAreaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shelter_area(
    organizationId: UUID,  # noqa: N803
    payload: ShelterAreaCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ShelterAreaResponse:
    _require_membership_admin(context, organizationId)
    _require_active_organization(await OrganizationRepository(session).get(organizationId))
    area = await ShelterAreaRepository(session, organizationId).add(
        name=payload.name, area_type=payload.area_type, parent_id=payload.parent_id
    )
    await AuditService(session).record(
        organization_id=organizationId,
        actor_user_id=context.user_id,
        action="shelter_area.created",
        resource_type="shelter_area",
        resource_id=area.id,
        source_channel="api",
        after={"name": area.name, "area_type": area.area_type},
    )
    await session.commit()
    return _area_response(area)


@router.patch(
    "/v1/organizations/{organizationId}/areas/{areaId}",
    response_model=ShelterAreaResponse,
)
async def update_shelter_area(
    organizationId: UUID,  # noqa: N803
    areaId: UUID,  # noqa: N803
    payload: ShelterAreaUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> ShelterAreaResponse:
    _require_membership_admin(context, organizationId)
    _require_active_organization(await OrganizationRepository(session).get(organizationId))
    area = await ShelterAreaRepository(session, organizationId).update(
        areaId, **payload.model_dump(exclude_none=True)
    )
    await AuditService(session).record(
        organization_id=organizationId,
        actor_user_id=context.user_id,
        action="shelter_area.updated",
        resource_type="shelter_area",
        resource_id=area.id,
        source_channel="api",
        after=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    return _area_response(area)
