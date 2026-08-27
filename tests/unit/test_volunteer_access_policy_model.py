from uuid import uuid4

from services.api.app.persistence.models.volunteer_access import OrganizationVolunteerAccessPolicy
from sqlalchemy import Boolean


def test_policy_insurance_required_column_is_fail_safe_boolean() -> None:
    column = OrganizationVolunteerAccessPolicy.__table__.c.insurance_required

    assert isinstance(column.type, Boolean)
    assert column.nullable is False
    assert column.default is not None
    assert column.default.arg is False
    assert column.server_default is not None
    assert str(column.server_default.arg).lower() == "false"


def test_policy_can_be_constructed_with_insurance_requirement_omitted_or_enabled() -> None:
    omitted = OrganizationVolunteerAccessPolicy(organization_id=uuid4())
    enabled = OrganizationVolunteerAccessPolicy(organization_id=uuid4(), insurance_required=True)

    assert omitted.organization_id is not None
    assert enabled.insurance_required is True


def test_policy_duration_defaults_to_seven_days_in_python_and_database() -> None:
    column = OrganizationVolunteerAccessPolicy.__table__.c.default_grant_duration_hours

    assert column.nullable is False
    assert column.default is not None
    assert column.default.arg == 168
    assert column.server_default is not None
    assert str(column.server_default.arg) == "168"
