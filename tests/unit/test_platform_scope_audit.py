from uuid import uuid4

import pytest
from services.api.app.application.audit_service import AuditService


@pytest.mark.asyncio
async def test_platform_audit_requires_platform_resource_when_scope_is_global():
    class Session:
        def add(self, record):
            self.record = record

        async def flush(self):
            return None

    audit = AuditService(Session())
    record = await audit.record(
        organization_id=None,
        actor_user_id=uuid4(),
        action="organization.created",
        resource_type="organization",
        resource_id=uuid4(),
        source_channel="api",
    )
    assert record.organization_id is None
    assert record.action == "organization.created"


@pytest.mark.asyncio
async def test_tenant_operation_audit_cannot_be_written_without_organization_scope():
    class Session:
        def add(self, record):
            self.record = record

        async def flush(self):
            return None

    with pytest.raises(ValueError, match="tenant business audit"):
        await AuditService(Session()).record(
            organization_id=None,
            actor_user_id=uuid4(),
            action="membership.created",
            resource_type="organization_membership",
            resource_id=uuid4(),
            source_channel="api",
        )
