from uuid import uuid4

import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import require_admin_context


def _context(role: str) -> RequestContext:
    return RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        membership_id=uuid4(),
        role=role,
    )


def test_volunteer_cannot_reach_management_settings_policy() -> None:
    with pytest.raises(DomainError) as error:
        require_admin_context(_context("VOLUNTEER"))
    assert error.value.status_code == 403


def test_shelter_admin_is_allowed_to_manage_scoped_settings() -> None:
    assert require_admin_context(_context("SHELTER_ADMIN"))
