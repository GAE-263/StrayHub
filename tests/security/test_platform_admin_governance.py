from uuid import uuid4

import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import require_platform_scope


def test_platform_route_requires_platform_scope_and_role() -> None:
    with pytest.raises(DomainError, match="平台管理員"):
        require_platform_scope(
            RequestContext(
                user_id=uuid4(),
                organization_id=None,
                membership_id=None,
                role="SHELTER_ADMIN",
                platform_scope=False,
            )
        )


def test_platform_route_does_not_require_shelter_context() -> None:
    require_platform_scope(
        RequestContext(
            user_id=uuid4(),
            organization_id=None,
            membership_id=None,
            role="PLATFORM_ADMIN",
            platform_scope=True,
        )
    )
