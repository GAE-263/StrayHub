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
async def test_sorted_options_can_share_one_operation_id_and_report_success() -> None:
    session = FakeSession()
    service = AuditService(session)  # type: ignore[arg-type]
    organization_id = uuid4()
    actor_id = uuid4()
    operation_id = uuid4()

    for option_id, before_order, after_order in (
        (uuid4(), 1, 0),
        (uuid4(), 0, 1),
    ):
        await service.record(
            organization_id=organization_id,
            actor_user_id=actor_id,
            operation_id=operation_id,
            action="observation_option.reordered",
            resource_type="ObservationOption",
            resource_id=option_id,
            source_channel="api",
            before={"display_order": before_order},
            after={"display_order": after_order},
            result="success",
        )

    assert len(session.values) == 2
    assert {record.operation_id for record in session.values} == {operation_id}
    assert {record.result for record in session.values} == {"success"}
    assert all(record.organization_id == organization_id for record in session.values)
    assert all(record.actor_user_id == actor_id for record in session.values)
