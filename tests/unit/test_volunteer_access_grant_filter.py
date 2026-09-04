from uuid import uuid4

import pytest
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)


class _Result:
    def scalars(self) -> list[object]:
        return []


class _Session:
    def __init__(self) -> None:
        self.statements: list[object] = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


@pytest.mark.asyncio
async def test_grant_user_filter_remains_tenant_scoped() -> None:
    organization_id = uuid4()
    user_id = uuid4()
    session = _Session()

    await VolunteerAccessRepository(session, organization_id).list_grants(user_id=user_id)

    statement = session.statements[0]
    sql = str(statement)
    assert "volunteer_access_grants.organization_id" in sql
    assert "volunteer_access_grants.user_id" in sql
    values = list(statement.compile().params.values())
    assert organization_id in values
    assert user_id in values
