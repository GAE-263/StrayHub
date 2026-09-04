from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from uuid import UUID

from fastapi import Request
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError

_LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1"})
_TRUSTED_CLIENT_IP_HEADER = "x-strayhub-trusted-client-ip"


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


MANAGEMENT_ROLES = {"PLATFORM_ADMIN", "SHELTER_ADMIN", "STAFF"}
ADMIN_ROLES = {"PLATFORM_ADMIN", "SHELTER_ADMIN"}


def require_management_context(
    context: RequestContext,
    *,
    roles: Iterable[str] = MANAGEMENT_ROLES,
) -> UUID:
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
