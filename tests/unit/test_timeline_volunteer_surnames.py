from uuid import UUID, uuid4

import pytest
from services.api.app.persistence.repositories.timeline_repository import TimelineRepository


class _Result:
    def __init__(self, rows: list[tuple[UUID, str | None, str | None]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[UUID, str | None, str | None]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[tuple[UUID, str | None, str | None]]) -> None:
        self.rows = rows
        self.statements: list[object] = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.rows)


@pytest.mark.asyncio
async def test_volunteer_label_lookup_is_tenant_and_membership_scoped() -> None:
    organization_id = uuid4()
    membership_id = uuid4()
    session = _Session([(membership_id, "黃", "V024")])

    result = await TimelineRepository(session, organization_id).volunteer_labels([membership_id])

    assert result == {membership_id: ("黃", "V024")}
    statement = session.statements[0]
    sql = str(statement)
    assert "organization_memberships.organization_id" in sql
    assert "organization_memberships.id IN" in sql
    assert "volunteer_profiles" in sql
    values = list(statement.compile().params.values())
    assert organization_id in values
    assert [membership_id] in values


@pytest.mark.asyncio
async def test_empty_volunteer_label_lookup_does_not_query() -> None:
    session = _Session([])

    assert await TimelineRepository(session, uuid4()).volunteer_labels([]) == {}
    assert session.statements == []
