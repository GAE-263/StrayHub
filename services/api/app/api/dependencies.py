from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, Header, Request
from services.api.app.api.errors import DomainError
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
from services.api.app.persistence.database.engine import get_session
from services.api.app.persistence.database.scope import (
    set_authentication_user_scope,
    set_organization_scope,
    set_platform_scope,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RequestContext:
    user_id: UUID
    organization_id: UUID | None
    membership_id: UUID | None
    role: str
    platform_scope: bool = False
    session_id: UUID | None = None


async def request_session(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AsyncIterator[AsyncSession]:
    yield session


async def current_request_context(
    request: Request,
    session: AsyncSession = Depends(request_session),  # noqa: B008
    authorization: str | None = Header(default=None),  # noqa: B008
    x_session_id: UUID | None = Header(default=None),  # noqa: B008
) -> RequestContext:
    """從 verified Access Token／Server-side Session 建立不可由前端覆寫的 Scope。"""

    context = getattr(request.state, "auth_context", None)
    if not isinstance(context, RequestContext):
        context = await _load_request_context(
            session,
            authorization=authorization,
            session_id=x_session_id,
        )
        request.state.auth_context = context
    return context


async def _load_request_context(
    session: AsyncSession,
    *,
    authorization: str | None,
    session_id: UUID | None,
) -> RequestContext:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise DomainError("authentication_required", "請先完成身分驗證", 401)
        settings = get_settings()
        if not settings.auth_jwt_active_public_key:
            raise DomainError("authentication_not_configured", "Authentication 金鑰尚未設定", 503)
        public_keys = {
            settings.auth_jwt_active_public_key_reference: settings.auth_jwt_active_public_key
        }
        if (
            settings.auth_jwt_previous_public_key
            and settings.auth_jwt_previous_public_key_reference
        ):
            public_keys[settings.auth_jwt_previous_public_key_reference] = (
                settings.auth_jwt_previous_public_key
            )
        try:
            claims = JwtAccessTokenAdapter(
                private_key="",
                public_keys=public_keys,
                issuer=settings.auth_jwt_issuer,
                audience=settings.auth_jwt_audience,
                ttl_seconds=settings.session_access_token_ttl_seconds,
                active_kid=settings.auth_jwt_active_public_key_reference,
            ).verify(token)
            session_id = UUID(str(claims["sid"]))
            token_user_id = UUID(str(claims["sub"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError("invalid_access_token", "Access Token 無效", 401) from exc
    if session_id is None:
        raise DomainError("authentication_required", "請先完成身分驗證", 401)

    repository = AuthenticationRepository(session)
    session_record = await repository.get_session(session_id)
    if (
        session_record is None
        or session_record.status != "active"
        or session_record.expires_at <= datetime.now(timezone.utc)
    ):
        raise DomainError("invalid_session", "Session 無效", 401)
    user = await repository.get_user(session_record.user_id)
    if user is None or user.status != "active":
        raise DomainError("invalid_session", "使用者無效", 401)
    if authorization and token_user_id != user.id:
        raise DomainError("invalid_access_token", "Access Token 無效", 401)

    platform_scope = user.platform_role == "PLATFORM_ADMIN"
    if platform_scope:
        await set_platform_scope(session)
    else:
        await set_authentication_user_scope(session, user.id)
    organization_id = session_record.active_organization_id
    membership_id = None
    role = user.platform_role or ""
    if organization_id is not None:
        organization = await repository.get_organization(organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("organization_disabled", "收容所目前停用", 403)
        membership = await repository.get_membership(user.id, organization_id)
        if membership is not None and membership.status == "active":
            membership_id = membership.id
            if not platform_scope:
                role = membership.role
        elif not platform_scope:
            raise DomainError("organization_access_denied", "無法存取此收容所資料", 404)
    elif not platform_scope:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)

    if not platform_scope:
        await set_organization_scope(session, organization_id)
    return RequestContext(
        user_id=user.id,
        organization_id=organization_id,
        membership_id=membership_id,
        role=role,
        platform_scope=platform_scope,
        session_id=session_record.id,
    )
