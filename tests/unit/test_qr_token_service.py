from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.reportable_scope_service import can_report
from services.api.app.domain.tenant_context import TenantContext


def test_animal_selection_requires_same_organization() -> None:
    org_a = uuid4()
    org_b = uuid4()
    with pytest.raises(DomainError, match="其他收容所"):
        can_report(
            organization_id=org_a,
            animal_organization_id=org_b,
            animal_status="active",
            scope_active=True,
        )


def test_platform_context_is_not_a_client_supplied_org_override() -> None:
    context = TenantContext(
        user_id=uuid4(), organization_id=uuid4(), role="PLATFORM_ADMIN", platform_scope=True
    )
    context.require_organization(uuid4())
