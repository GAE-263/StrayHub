from __future__ import annotations

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.identity import OrganizationMembership, User


def require_platform_admin(user: User) -> None:
    if user.status != "active" or user.platform_role != "PLATFORM_ADMIN":
        raise DomainError("platform_admin_required", "需要平台管理員權限", 403)


def require_role(
    user: User,
    membership: OrganizationMembership | None,
    *roles: str,
) -> None:
    if user.status != "active":
        raise DomainError("role_required", "目前帳號無法執行此操作", 403)
    if user.platform_role == "PLATFORM_ADMIN":
        return
    if membership is None or membership.status != "active" or membership.role not in roles:
        raise DomainError("role_required", "目前帳號無法執行此操作", 403)
