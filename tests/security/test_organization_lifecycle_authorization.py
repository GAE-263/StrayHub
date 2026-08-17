from uuid import uuid4

import pytest
from services.api.app.api import organization_management as api
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError


def test_non_platform_context_cannot_use_platform_lifecycle_policy():
    with pytest.raises(DomainError) as error:
        api._require_platform(
            RequestContext(
                user_id=uuid4(),
                organization_id=uuid4(),
                membership_id=uuid4(),
                role="SHELTER_ADMIN",
                platform_scope=False,
            )
        )
    assert error.value.code == "platform_admin_required"
    assert error.value.status_code == 403


@pytest.mark.parametrize("role", ["STAFF", "VOLUNTEER"])
def test_staff_and_volunteer_cannot_manage_current_shelter_settings(role: str):
    with pytest.raises(DomainError) as error:
        api._require_organization_settings_admin(
            RequestContext(
                user_id=uuid4(),
                organization_id=uuid4(),
                membership_id=uuid4(),
                role=role,
                platform_scope=False,
            ),
            uuid4(),
        )
    assert error.value.code == "organization_settings_denied"
    assert error.value.status_code == 403


def test_cross_organization_shelter_admin_cannot_change_timezone():
    current_org = uuid4()
    other_org = uuid4()
    with pytest.raises(DomainError) as error:
        api._require_update_permission(
            RequestContext(
                user_id=uuid4(),
                organization_id=current_org,
                membership_id=uuid4(),
                role="SHELTER_ADMIN",
                platform_scope=False,
            ),
            other_org,
            api.OrganizationUpdateRequest(timezone="UTC"),
        )
    assert error.value.status_code == 403
