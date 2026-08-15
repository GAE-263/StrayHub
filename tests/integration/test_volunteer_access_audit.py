from uuid import uuid4

import pytest
from services.api.app.api.dependencies import (
    RequestContext,
    platform_support_audit_lifecycle,
)
from services.api.app.api.errors import DomainError


@pytest.mark.asyncio
async def test_platform_support_lifecycle_records_success_and_denied_terminal_results() -> None:
    records = []

    class Audit:
        async def record(self, **record):
            records.append(record)

    context = RequestContext(
        user_id=uuid4(),
        organization_id=None,
        membership_id=None,
        role="PLATFORM_ADMIN",
        platform_scope=True,
    )
    organization_id = uuid4()
    async with platform_support_audit_lifecycle(
        Audit(),
        context=context,
        target_organization_id=organization_id,
        support_reason="協助排查通知",
        resource_type="volunteer_notification_delivery",
    ):
        pass
    with pytest.raises(DomainError):
        async with platform_support_audit_lifecycle(
            Audit(),
            context=context,
            target_organization_id=organization_id,
            support_reason="協助排查通知",
            resource_type="volunteer_notification_delivery",
        ):
            raise DomainError("not_found", "not found", 404)
    assert [record["result"] for record in records] == ["success", "not_found"]
    assert all(record["organization_id"] == organization_id for record in records)
    assert all(record["reason"] == "協助排查通知" for record in records)
