from uuid import uuid4

from services.api.app.persistence.models.identity import User
from services.api.app.persistence.models.platform_governance import PlatformAdminPolicy


def platform_policy_fixture() -> PlatformAdminPolicy:
    return PlatformAdminPolicy(
        id=uuid4(),
        policy_key="default",
        min_active_admins=1,
        max_active_admins=2,
        version=1,
    )


def platform_user_fixture(
    *,
    username: str = "platform-admin",
    display_name: str = "平台管理員",
    status: str = "active",
    platform_role: str | None = "PLATFORM_ADMIN",
) -> User:
    return User(
        id=uuid4(),
        username=username,
        display_name=display_name,
        status=status,
        platform_role=platform_role,
    )
