from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from services.api.app.api import volunteer_access as api
from services.api.app.persistence.repositories.organization_repository import OrganizationRepository


class _ProjectionResult:
    def __init__(self, rows: list[tuple[UUID, str, str, str | None, bool]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[UUID, str, str, str | None, bool]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[tuple[UUID, str, str, str | None, bool]]) -> None:
        self.rows = rows
        self.statements = []
        self.events = []

    async def execute(self, statement):
        self.events.append("read")
        self.statements.append(statement)
        return _ProjectionResult(self.rows)


@pytest.mark.asyncio
async def test_public_directory_projects_active_enabled_organizations_in_stable_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_id = uuid4()
    second_id = uuid4()
    rows = [
        (first_id, "ORG-ALPHA", "Alpha Shelter", "north", False),
        (second_id, "ORG-BETA", "Beta Shelter", None, True),
    ]
    session = _Session(rows)
    scopes: list[object] = []

    async def record_public_directory_scope(received_session) -> None:
        received_session.events.append("scope")
        scopes.append(received_session)

    monkeypatch.setattr(
        "services.api.app.persistence.repositories.organization_repository.set_public_volunteer_directory_scope",
        record_public_directory_scope,
    )

    organizations = await OrganizationRepository(session).list_public_volunteer_organizations()

    assert organizations == rows
    assert scopes == [session]
    assert session.events == ["scope", "read"]
    assert len(session.statements) == 1
    sql = str(session.statements[0])
    assert "organizations" in sql
    assert "organization_volunteer_access_policies" in sql
    assert "ORDER BY organizations.name, organizations.code, organizations.id" in sql
    assert "organization_memberships" not in sql
    assert "volunteer_applications" not in sql


@pytest.mark.asyncio
async def test_public_directory_route_is_unauthenticated_and_returns_only_public_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()

    class _Repository:
        def __init__(self, _session) -> None:
            pass

        async def list_public_volunteer_organizations(self):
            return [(organization_id, "ORG-PUBLIC", "Public Shelter", "east", True)]

    monkeypatch.setattr(api, "OrganizationRepository", _Repository)
    response = await api.list_public_volunteer_organizations(object())

    assert [item.model_dump() for item in response] == [
        {
            "id": organization_id,
            "code": "ORG-PUBLIC",
            "name": "Public Shelter",
            "service_area": "east",
            "insurance_required": True,
        }
    ]
