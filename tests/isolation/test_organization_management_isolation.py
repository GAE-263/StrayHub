from pathlib import Path
from uuid import uuid4

import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.organization_management import _require_membership_admin


def test_shelter_area_storage_has_forced_rls_and_tenant_policy():
    migration = Path("services/api/migrations/versions/0008_shelter_areas.py").read_text()
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "app.current_org_id" in migration
    assert "app.platform_scope" in migration


def test_shelter_admin_cannot_use_another_organization_identifier():
    context = RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        membership_id=uuid4(),
        role="SHELTER_ADMIN",
    )
    with pytest.raises(DomainError, match="無法管理"):
        _require_membership_admin(context, uuid4())
