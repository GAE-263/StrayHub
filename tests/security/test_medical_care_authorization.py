from uuid import uuid4

import pytest
from services.api.app.api.dependencies import RequestContext, validate_platform_support_request
from services.api.app.api.errors import DomainError
from services.api.app.domain.medical_care_access import permission_for, require_medical_view


@pytest.mark.parametrize("role", ["SHELTER_ADMIN", "PLATFORM_ADMIN"])
def test_admin_roles_have_full_medical_permission(role: str) -> None:
    permission = permission_for(role=role, membership_active=True, medical_care_access=False)
    assert permission.can_view and permission.can_manage_records
    assert permission.can_manage_series and permission.can_process_occurrences


def test_staff_requires_active_membership_and_explicit_capability() -> None:
    assert permission_for(
        role="STAFF", membership_active=True, medical_care_access=True
    ).can_manage_records
    for active, access in ((False, True), (True, False), (False, False)):
        permission = permission_for(
            role="STAFF", membership_active=active, medical_care_access=access
        )
        with pytest.raises(DomainError):
            require_medical_view(permission)


def test_volunteer_never_receives_full_medical_payload() -> None:
    permission = permission_for(role="VOLUNTEER", membership_active=True, medical_care_access=True)
    assert permission.assigned_only
    assert not permission.can_view


def test_platform_admin_requires_single_target_and_support_reason() -> None:
    context = RequestContext(
        user_id=uuid4(),
        organization_id=None,
        membership_id=None,
        role="PLATFORM_ADMIN",
        platform_scope=True,
    )
    target = uuid4()
    assert validate_platform_support_request(context, target, "協助調查") == "協助調查"
    with pytest.raises(DomainError):
        validate_platform_support_request(context, target, "")


def test_medical_audit_query_rechecks_medical_capability() -> None:
    source = __import__("pathlib").Path("services/api/app/api/audit.py").read_text()
    assert '"MedicalRecord"' in source
    assert "medical_permission(session, context)" in source
    assert "require_medical_view" in source
