from uuid import uuid4

import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.volunteer_access import require_volunteer_management


def test_only_target_shelter_admin_or_scoped_platform_support_can_manage() -> None:
    organization_id = uuid4()
    shelter_admin = RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        role="SHELTER_ADMIN",
    )
    require_volunteer_management(shelter_admin, organization_id, None)

    for role in ("STAFF", "VOLUNTEER"):
        with pytest.raises(DomainError):
            require_volunteer_management(
                RequestContext(
                    user_id=uuid4(),
                    organization_id=organization_id,
                    membership_id=uuid4(),
                    role=role,
                ),
                organization_id,
                None,
            )
    with pytest.raises(DomainError):
        require_volunteer_management(shelter_admin, uuid4(), None)

    platform = RequestContext(
        user_id=uuid4(),
        organization_id=None,
        membership_id=None,
        role="PLATFORM_ADMIN",
        platform_scope=True,
    )
    with pytest.raises(DomainError, match="支援原因"):
        require_volunteer_management(platform, organization_id, None)
    assert require_volunteer_management(platform, organization_id, "協助排查") == "協助排查"
