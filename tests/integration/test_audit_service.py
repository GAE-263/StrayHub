from uuid import uuid4

import pytest
from services.api.app.application.audit_service import AuditService


class FakeSession:
    def __init__(self) -> None:
        self.values = []

    def add(self, value) -> None:
        self.values.append(value)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_audit_service_records_scope_switch_and_correction() -> None:
    session = FakeSession()
    service = AuditService(session)  # type: ignore[arg-type]
    organization_id = uuid4()
    actor_id = uuid4()

    switch = await service.record_scope_switch(
        actor_user_id=actor_id, organization_id=organization_id
    )
    correction = await service.record_correction(
        organization_id=organization_id,
        actor_user_id=actor_id,
        resource_type="CareReport",
        resource_id=uuid4(),
        before={"value": "old"},
        after={"value": "new"},
    )

    assert switch.action == "scope_switch"
    assert correction.action == "correction"
    assert len(session.values) == 2


@pytest.mark.asyncio
async def test_audit_service_rejects_unscoped_business_record() -> None:
    service = AuditService(FakeSession())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="organization scope"):
        await service.record(
            organization_id=None,
            actor_user_id=None,
            action="read",
            resource_type="CareReport",
            source_channel="api",
        )
