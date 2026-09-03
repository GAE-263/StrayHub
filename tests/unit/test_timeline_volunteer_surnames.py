from uuid import UUID, uuid4

import pytest
from services.api.app.persistence.repositories.timeline_repository import TimelineRepository


class _Result:
    def __init__(self, rows: list[tuple[UUID, str]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[UUID, str]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[tuple[UUID, str]]) -> None:
        self.rows = rows
        self.statements: list[object] = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.rows)


@pytest.mark.asyncio
async def test_volunteer_surname_lookup_is_tenant_and_user_scoped() -> None:
    organization_id = uuid4()
    user_id = uuid4()
    session = _Session([(user_id, "黃")])

    result = await TimelineRepository(session, organization_id).volunteer_surnames([user_id])

    assert result == {user_id: "黃"}
    statement = session.statements[0]
    sql = str(statement)
    assert "organization_memberships.organization_id" in sql
    assert "organization_memberships.user_id IN" in sql
    values = list(statement.compile().params.values())
    assert organization_id in values
    assert [user_id] in values


@pytest.mark.asyncio
async def test_empty_volunteer_surname_lookup_does_not_query() -> None:
    session = _Session([])

    assert await TimelineRepository(session, uuid4()).volunteer_surnames([]) == {}
    assert session.statements == []
