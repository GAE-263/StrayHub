from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.authentication.context_service import ActiveShelterContextService
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.infrastructure.line.identity_verification_adapter import LineIdentityVerifier
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
    id_token: str


class ShelterContextSwitchRequest(BaseModel):
    organization_id: UUID


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
        line_verifier=LineIdentityVerifier(settings.line_channel_id),
        refresh_ttl_seconds=settings.session_refresh_token_ttl_seconds,
        access_ttl_seconds=settings.session_access_token_ttl_seconds,
    )


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    service: SessionService = Depends(get_session_service),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:  # noqa: B008
    result = await service.login(username=payload.username, password=payload.password)
    await session.commit()
    return result


@router.post("/refresh", status_code=status.HTTP_200_OK)
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


@router.post("/liff/exchange", status_code=status.HTTP_200_OK)
async def liff_exchange(
    payload: LiffExchangeRequest,
    service: SessionService = Depends(get_session_service),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    result = await service.exchange_line_identity(id_token=payload.id_token)
    await session.commit()
    return result


@router.get("/me")
async def current_user(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    service: SessionService = Depends(get_session_service),  # noqa: B008
) -> dict:
    if context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)
    return await service.current_user(session_id=context.session_id)


@router.get("/active-shelter-context")
async def active_context(
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)
    context = await ActiveShelterContextService(AuthenticationRepository(session)).get(
        session_id=context.session_id
    )
    return {"organization_id": context.active_organization_id, "session_id": context.id}


@router.put("/active-shelter-context")
async def switch_context(
    payload: ShelterContextSwitchRequest,
    request_context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    if request_context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)
    context = await ActiveShelterContextService(
        AuthenticationRepository(session), audit=AuditService(session)
    ).switch(session_id=request_context.session_id, organization_id=payload.organization_id)
    await session.commit()
    return {"organization_id": context.active_organization_id, "session_id": context.id}
