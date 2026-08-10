from uuid import uuid4

import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import (
    require_admin_context,
    require_management_context,
)


def _context(role: str, organization_id=None) -> RequestContext:
    return RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4() if organization_id else None,
        role=role,
    )


@pytest.mark.parametrize("role", ["PLATFORM_ADMIN", "SHELTER_ADMIN", "STAFF"])
def test_management_roles_require_an_active_shelter_context(role: str) -> None:
    organization_id = uuid4()
    assert require_management_context(_context(role, organization_id)) == organization_id


def test_volunteer_is_denied_from_management_workbench() -> None:
    with pytest.raises(DomainError, match="管理工作台"):
        require_management_context(_context("VOLUNTEER", uuid4()))


def test_missing_shelter_context_is_a_conflict() -> None:
    with pytest.raises(DomainError) as error:
        require_management_context(_context("STAFF"))

    assert error.value.status_code == 409


def test_staff_cannot_use_admin_only_settings() -> None:
    with pytest.raises(DomainError) as error:
        require_admin_context(_context("STAFF", uuid4()))

    assert error.value.status_code == 403
