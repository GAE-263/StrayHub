from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError

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
