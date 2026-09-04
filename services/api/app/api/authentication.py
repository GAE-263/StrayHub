from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from services.api.app.api.dependencies import (
    RequestContext,
    authenticated_request_context,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import resolve_trusted_client_ip
from services.api.app.application.audit_service import AuditService
from services.api.app.application.authentication.context_service import ActiveShelterContextService
from services.api.app.application.authentication.login_abuse import LoginAbuseKeys
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.application.line_rich_menu_routing import (
    RichMenuRoutingService,
    build_registry,
)
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.infrastructure.line.entry_reference_adapter import (
    VolunteerEntryReferenceAdapter,
)
from services.api.app.infrastructure.line.identity_verification_adapter import (
    configured_line_identity_verifier,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LiffExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=1, max_length=8192)
    shelter_entry_reference: str = Field(min_length=32, max_length=512)


class LiffExchangeOrganization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str


class LiffExchangeVolunteerUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["VOLUNTEER"]


class LiffExchangeNewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["NEW"]
    organization: LiffExchangeOrganization
    next_path: Literal["/volunteer-application"]


class LiffExchangePendingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["PENDING"]
    organization: LiffExchangeOrganization


class LiffExchangeActiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["ACTIVE"]
    access_token: str
    refresh_token: str
    expires_in: int
    session_id: UUID
    user_id: UUID
    user: LiffExchangeVolunteerUser
    organization: LiffExchangeOrganization
    next_path: Literal["/animal-confirmation"]


class LiffExchangeSuspendedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["SUSPENDED"]
    organization: LiffExchangeOrganization


LiffExchangeResponse = Annotated[
    LiffExchangeNewResponse
    | LiffExchangePendingResponse
    | LiffExchangeActiveResponse
    | LiffExchangeSuspendedResponse,
    Field(discriminator="state"),
]


class ShelterContextSwitchRequest(BaseModel):
    organization_id: UUID


class CurrentUserAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership_id: UUID
    organization_id: UUID
    status: Literal["active", "expired", "revoked"]
    valid_from: datetime
    expires_at: datetime


class CurrentUserCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_view_medical_care: bool
    can_manage_series: bool


class CurrentUserMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: Literal["SHELTER_ADMIN", "STAFF", "VOLUNTEER"]
    status: Literal["invited", "active", "disabled", "expired", "revoked", "archived"]
    valid_from: datetime | None
    expires_at: datetime | None
    access_grant: CurrentUserAccessGrant | None
    medical_care_access: bool
    capabilities: CurrentUserCapabilities


class CurrentUserProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    username: str | None
    display_name: str | None
    platform_role: str | None
    status: Literal["active", "disabled"]


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: CurrentUserProfile
    memberships: list[CurrentUserMembership]


def get_session_service(_session: AsyncSession = Depends(request_session)) -> SessionService:  # noqa: B008
    settings = get_settings()
    if not settings.auth_jwt_active_private_key or not settings.auth_jwt_active_public_key:
        raise DomainError("authentication_not_configured", "Authentication 金鑰尚未設定", 503)
    public_keys = {
        settings.auth_jwt_active_public_key_reference: settings.auth_jwt_active_public_key
    }
    if settings.auth_jwt_previous_public_key and settings.auth_jwt_previous_public_key_reference:
        public_keys[settings.auth_jwt_previous_public_key_reference] = (
            settings.auth_jwt_previous_public_key
        )
    rich_menu_router = None
    registry = build_registry()
    if settings.line_role_menu_features_active():
        registry = build_registry(
            default=settings.line_rich_menu_default_id,
            volunteer=settings.line_rich_menu_volunteer_id,
            adopter=settings.line_rich_menu_adopter_id,
            staff=settings.line_rich_menu_staff_id,
        )
    if registry.menu_ids:
        from services.api.app.infrastructure.line.messaging_api_adapter import (
            LineMessagingApiAdapter,
        )

        rich_menu_router = RichMenuRoutingService(LineMessagingApiAdapter(), registry)
    return SessionService(
        AuthenticationRepository(_session),
        password_hasher=Argon2PasswordHasher(),
        access_token=JwtAccessTokenAdapter(
            private_key=settings.auth_jwt_active_private_key,
            public_keys=public_keys,
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            ttl_seconds=settings.session_access_token_ttl_seconds,
            active_kid=settings.auth_jwt_active_public_key_reference,
        ),
        line_verifier=configured_line_identity_verifier(
            app_env=settings.app_env,
            channel_id=settings.line_login_channel_id or settings.line_channel_id,
        ),
        entry_resolver=VolunteerEntryReferenceAdapter(_session),
        rich_menu_router=rich_menu_router,
        refresh_ttl_seconds=settings.session_refresh_token_ttl_seconds,
        access_ttl_seconds=settings.session_access_token_ttl_seconds,
        abuse_keys=LoginAbuseKeys(settings.login_abuse_hmac_secret),
    )


@router.post("/login", status_code=status.HTTP_200_OK, openapi_extra={"security": []})
async def login(
    request: Request,
    payload: LoginRequest,
    service: SessionService = Depends(get_session_service),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:  # noqa: B008
    settings = get_settings()
    try:
        client_ip = resolve_trusted_client_ip(
            request,
            trusted_proxy_enabled=settings.login_trusted_proxy_enabled,
            allow_local_test_peer=settings.app_env.strip().lower() in {"local", "test", "testing"},
        )
    except ValueError as exc:
        raise DomainError("login_source_unavailable", "登入暫時無法處理", 503) from exc
    try:
        result = await service.login(
            username=payload.username,
            password=payload.password,
            client_ip=client_ip,
        )
    except DomainError:
        await session.commit()
        raise
    await session.commit()
    return result


@router.post("/refresh", status_code=status.HTTP_200_OK, openapi_extra={"security": []})
async def refresh(
    payload: RefreshRequest,
    service: SessionService = Depends(get_session_service),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:  # noqa: B008
    result = await service.refresh(refresh_token=payload.refresh_token)
    await session.commit()
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    service: SessionService = Depends(get_session_service),  # noqa: B008
) -> Response:
    if context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)
    await service.logout(session_id=context.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/liff/exchange",
    status_code=status.HTTP_200_OK,
    response_model=LiffExchangeResponse,
    openapi_extra={"security": []},
)
async def liff_exchange(
    payload: LiffExchangeRequest,
    service: SessionService = Depends(get_session_service),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> LiffExchangeResponse:
    result = await service.exchange_line_identity(
        id_token=payload.id_token,
        shelter_entry_reference=payload.shelter_entry_reference,
    )
    try:
        response = TypeAdapter(LiffExchangeResponse).validate_python(result)
        await session.commit()
    except Exception as exc:
        try:
            await session.rollback()
        except Exception:
            pass
        raise DomainError("liff_exchange_unavailable", "志工入口暫時無法使用", 503) from exc
    return response


@router.get("/me", response_model=CurrentUserResponse)
async def current_user(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    service: SessionService = Depends(get_session_service),  # noqa: B008
) -> CurrentUserResponse:
    if context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)
    return CurrentUserResponse.model_validate(
        await service.current_user(session_id=context.session_id)
    )


@router.get("/active-shelter-context")
async def active_context(
    request_context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if request_context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)
    repository = AuthenticationRepository(session)
    active_session = await ActiveShelterContextService(repository).get(
        session_id=request_context.session_id
    )
    if active_session.active_organization_id is None:
        raise DomainError("invalid_context", "目前收容所無效", 409)
    organization = await repository.get_organization(active_session.active_organization_id)
    if organization is None:
        raise DomainError("invalid_context", "目前收容所無效", 409)
    return {
        "organization_id": active_session.active_organization_id,
        "organization_name": organization.name,
        "session_id": active_session.id,
    }


@router.put("/active-shelter-context")
async def switch_context(
    payload: ShelterContextSwitchRequest,
    request_context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if request_context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)
    repository = AuthenticationRepository(session)
    try:
        context = await ActiveShelterContextService(repository, audit=AuditService(session)).switch(
            session_id=request_context.session_id, organization_id=payload.organization_id
        )
        if context.active_organization_id is None:
            raise DomainError("invalid_context", "目前收容所無效", 409)
        organization = await repository.get_organization(context.active_organization_id)
        if organization is None:
            raise DomainError("invalid_context", "目前收容所無效", 409)
        response = {
            "organization_id": context.active_organization_id,
            "organization_name": organization.name,
            "session_id": context.id,
        }
        await session.commit()
    except Exception:
        # Includes commit-time failures: no partial session or success audit,
        # and transaction-local scope is cleared before returning the safe error.
        await session.rollback()
        raise
    return response
