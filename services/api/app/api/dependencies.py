from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote
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
    set_platform_support_scope,
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


@dataclass
class PlatformSupportAuditLifecycle:
    result: str = "success"


def decode_platform_support_reason(support_reason: str | None) -> str:
    raw_reason = (support_reason or "").strip()
    try:
        return unquote(raw_reason, encoding="utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise DomainError(
            "invalid_platform_support_reason_encoding",
            "平台支援原因編碼無效",
            422,
        ) from exc


def validate_platform_support_request(
    context: RequestContext,
    target_organization_id: UUID | None,
    support_reason: str | None,
) -> str:
    if not context.platform_scope or context.role != "PLATFORM_ADMIN":
        raise DomainError("platform_admin_required", "需要平台管理員權限", 403)
    if not isinstance(target_organization_id, UUID):
        raise DomainError("platform_target_required", "平台支援必須指定單一收容所", 422)
    reason = decode_platform_support_reason(support_reason)
    if not reason:
        raise DomainError("platform_support_reason_required", "請填寫平台支援原因", 422)
    if len(reason) > 500:
        raise DomainError("platform_support_reason_too_long", "平台支援原因不得超過 500 字", 422)
    return reason


@asynccontextmanager
async def platform_support_audit_lifecycle(
    audit: Any,
    *,
    context: RequestContext,
    target_organization_id: UUID,
    support_reason: str,
    resource_type: str,
    session: AsyncSession | None = None,
) -> AsyncIterator[PlatformSupportAuditLifecycle]:
    """Record one terminal audit result for every scoped platform request."""
    lifecycle = PlatformSupportAuditLifecycle()
    failed = False
    try:
        yield lifecycle
    except DomainError as exc:
        failed = True
        lifecycle.result = "not_found" if exc.status_code == 404 else "denied"
        raise
    except Exception:
        failed = True
        lifecycle.result = "exception"
        raise
    finally:
        if failed and session is not None:
            await session.rollback()
            await set_platform_support_scope(session, target_organization_id)
        await audit.record(
            organization_id=target_organization_id,
            actor_user_id=context.user_id,
            action="platform_support.access",
            resource_type=resource_type,
            source_channel="api",
            reason=support_reason,
            result=lifecycle.result,
        )
        if failed and session is not None:
            await session.commit()


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
            require_organization=True,
        )
        request.state.auth_context = context
    return context


async def authenticated_request_context(
    request: Request,
    session: AsyncSession = Depends(request_session),  # noqa: B008
    authorization: str | None = Header(default=None),  # noqa: B008
    x_session_id: UUID | None = Header(default=None),  # noqa: B008
) -> RequestContext:
    """建立已驗證的使用者 Context，但允許尚未選定收容所的 Session。"""

    context = getattr(request.state, "auth_context", None)
    if not isinstance(context, RequestContext):
        context = await _load_request_context(
            session,
            authorization=authorization,
            session_id=x_session_id,
            require_organization=False,
        )
        request.state.auth_context = context
    return context


async def _load_request_context(
    session: AsyncSession,
    *,
    authorization: str | None,
    session_id: UUID | None,
    require_organization: bool = True,
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
        membership = await repository.get_effective_membership(user.id, organization_id)
        if membership is not None:
            membership_id = membership.id
            if not platform_scope:
                role = membership.role
        elif not platform_scope:
            raise DomainError("organization_access_denied", "無法存取此收容所資料", 404)
    elif not platform_scope and require_organization:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)

    if not platform_scope and organization_id is not None:
        await set_organization_scope(session, organization_id)
    return RequestContext(
        user_id=user.id,
        organization_id=organization_id,
        membership_id=membership_id,
        role=role,
        platform_scope=platform_scope,
        session_id=session_record.id,
    )


async def apply_platform_support_scope(
    session: AsyncSession,
    *,
    context: RequestContext,
    target_organization_id: UUID | None,
    support_reason: str | None,
) -> str:
    reason = validate_platform_support_request(context, target_organization_id, support_reason)
    assert target_organization_id is not None
    await set_platform_support_scope(session, target_organization_id)
    return reason
