from uuid import uuid4

import pytest
from services.api.app.api.dependencies import (
    RequestContext,
    platform_support_audit_lifecycle,
    validate_platform_support_request,
)
from services.api.app.api.errors import DomainError
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


@pytest.mark.asyncio
async def test_denial_audit_preserves_scope_reason_result_and_before_projection():
    class Session:
        def add(self, record):
            self.record = record

        async def flush(self):
            return None

    organization_id = uuid4()
    membership_id = uuid4()
    record = await AuditService(Session()).record_denial(
        organization_id=organization_id,
        actor_user_id=uuid4(),
        resource_type="organization_membership",
        resource_id=membership_id,
        reason="membership_state_changed",
        before={"role": "STAFF", "status": "active", "access_version": 3},
    )

    assert record.organization_id == organization_id
    assert record.resource_id == membership_id
    assert record.result == "denied"
    assert record.reason == "membership_state_changed"
    assert record.before_data == {"role": "STAFF", "status": "active", "access_version": 3}
    assert record.after_data is None


def test_platform_support_requires_one_target_and_trimmed_reason_before_query() -> None:
    target = uuid4()
    context = RequestContext(
        user_id=uuid4(),
        organization_id=None,
        membership_id=None,
        role="PLATFORM_ADMIN",
        platform_scope=True,
    )
    assert validate_platform_support_request(context, target, "  協助排查通知  ") == "協助排查通知"
    for reason in (None, "", "   "):
        with pytest.raises(DomainError, match="支援原因"):
            validate_platform_support_request(context, target, reason)


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ["success", "denied", "not_found", "validation", "exception"])
async def test_platform_support_audit_lifecycle_records_every_result(result: str) -> None:
    class RecordingAudit:
        def __init__(self) -> None:
            self.results = []

        async def record(self, **kwargs):
            self.results.append(kwargs)

    context = RequestContext(
        user_id=uuid4(),
        organization_id=None,
        membership_id=None,
        role="PLATFORM_ADMIN",
        platform_scope=True,
    )
    audit = RecordingAudit()
    async with platform_support_audit_lifecycle(
        audit,
        context=context,
        target_organization_id=uuid4(),
        support_reason="支援測試",
        resource_type="volunteer_application",
    ) as lifecycle:
        lifecycle.result = result

    assert audit.results[0]["result"] == result
    assert audit.results[0]["reason"] == "支援測試"
