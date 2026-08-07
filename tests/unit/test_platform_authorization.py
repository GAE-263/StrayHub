import pytest
from services.api.app.api.authorization import require_platform_admin
from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.identity import User


def test_platform_admin_does_not_need_membership() -> None:
    require_platform_admin(
        User(platform_role="PLATFORM_ADMIN", display_name="平台管理員", status="active")
    )


def test_shelter_role_cannot_use_platform_scope() -> None:
    with pytest.raises(DomainError, match="平台管理員"):
        require_platform_admin(User(platform_role=None, display_name="收容所管理員"))
