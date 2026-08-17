from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.medical_care_audit import medical_care_audit_lifecycle


class FakeSession:
    def __init__(self) -> None:
        self.values = []
        self.executed = []
        self.rolled_back = False
        self.committed = False

    def add(self, value) -> None:
        self.values.append(value)

    async def flush(self) -> None:
        pass

    async def rollback(self) -> None:
        self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    async def execute(self, statement, parameters=None):
        self.executed.append((statement, parameters))


@pytest.mark.asyncio
async def test_denial_audit_survives_business_transaction_rollback() -> None:
    session = FakeSession()
    organization_id = uuid4()
    with pytest.raises(DomainError):
        async with medical_care_audit_lifecycle(
            session,  # type: ignore[arg-type]
            organization_id=organization_id,
            actor_user_id=uuid4(),
            action="medical_record.access_denied",
            resource_type="MedicalRecord",
        ):
            raise DomainError("medical_care_access_denied", "無權存取", 403)
    assert session.rolled_back and session.committed
    assert session.values[0].result == "denied"
    assert session.values[0].organization_id == organization_id
