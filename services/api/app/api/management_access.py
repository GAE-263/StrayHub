from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Request
from services.api.app.api.errors import DomainError

if TYPE_CHECKING:
    from services.api.app.api.dependencies import RequestContext

_LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1"})
_TRUSTED_CLIENT_IP_HEADER = "x-strayhub-trusted-client-ip"
_PUBLIC_PROFILE_HEADER = "x-strayhub-public-profile"
PUBLIC_MANAGEMENT_PROFILES = frozenset({"shared-demo-production", "shared-demo-dev"})
REMOTE_MANAGEMENT_SESSION_ORIGIN = "remote_management_demo"


def resolve_trusted_client_ip(
    request: Request,
    *,
    trusted_proxy_enabled: bool,
    allow_local_test_peer: bool = False,
) -> str:
    """Resolve the login identity without trusting ordinary forwarding headers."""

    peer = request.client.host if request.client is not None else None
    try:
        if not trusted_proxy_enabled:
            if peer is None:
                raise ValueError
            if allow_local_test_peer and peer in {"testclient", "localhost"}:
                return "127.0.0.1"
            return str(ipaddress.ip_address(peer))
        if peer not in _LOOPBACK_PEERS:
            raise ValueError
        values = request.headers.getlist(_TRUSTED_CLIENT_IP_HEADER)
        if len(values) != 1 or "," in values[0]:
            raise ValueError
        return str(ipaddress.ip_address(values[0].strip()))
    except ValueError:
        raise ValueError("trusted client IP unavailable") from None


def resolve_public_exposure_profile(
    request: Request,
    *,
    trusted_proxy_enabled: bool,
) -> str | None:
    """Read profile metadata only from the configured loopback gateway hop."""

    values = request.headers.getlist(_PUBLIC_PROFILE_HEADER)
    if not values:
        return None
    peer = request.client.host if request.client is not None else None
    if (
        not trusted_proxy_enabled
        or peer not in _LOOPBACK_PEERS
        or len(values) != 1
        or "," in values[0]
        or values[0].strip() not in PUBLIC_MANAGEMENT_PROFILES
    ):
        raise ValueError("public exposure profile unavailable")
    return values[0].strip()


def enforce_session_exposure_profile(
    *, session_origin: str, persisted_profile: str | None, request_profile: str | None
) -> None:
    """Keep a remote session bound to the trusted profile that created it."""

    if session_origin == REMOTE_MANAGEMENT_SESSION_ORIGIN and request_profile != persisted_profile:
        raise DomainError("invalid_session", "Session 無效", 401)


MANAGEMENT_ROLES = {"PLATFORM_ADMIN", "SHELTER_ADMIN", "STAFF"}
ADMIN_ROLES = {"PLATFORM_ADMIN", "SHELTER_ADMIN"}


def enforce_public_management_role(context: RequestContext) -> None:
    if context.public_exposure_profile and context.role not in {"STAFF", "SHELTER_ADMIN"}:
        raise DomainError("management_access_denied", "目前帳號無法使用管理工作台", 403)


def require_management_context(
    context: RequestContext,
    *,
    roles: Iterable[str] = MANAGEMENT_ROLES,
) -> UUID:
    enforce_public_management_role(context)
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    if context.role not in set(roles):
        raise DomainError("management_access_denied", "目前帳號無法使用管理工作台", 403)
    return context.organization_id


def require_admin_context(context: RequestContext) -> UUID:
    return require_management_context(context, roles=ADMIN_ROLES)


def require_staff_or_admin(context: RequestContext) -> UUID:
    return require_management_context(context, roles=MANAGEMENT_ROLES)


def require_platform_scope(context: RequestContext) -> None:
    if not context.platform_scope or context.role != "PLATFORM_ADMIN":
        raise DomainError("platform_admin_required", "需要平台管理員權限", 403)
