from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.persistence.database.scope import (
    set_authentication_user_organization_scope,
)
from services.api.app.persistence.models.identity import LineUserBinding, OrganizationMembership
from services.api.app.persistence.models.volunteer_access import VolunteerAccessGrant
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))


@pytest.mark.asyncio
async def test_authentication_scope_keeps_exact_user_and_organization() -> None:
    session = RecordingSession()
    user_id = uuid4()
    organization_id = uuid4()

    await set_authentication_user_organization_scope(session, user_id, organization_id)

    assert session.calls == [
        (
            "SELECT set_config('app.auth_user_id', :user_id, true)",
            {"user_id": str(user_id)},
        ),
        (
            "SELECT set_config('app.auth_exact_org_id', :organization_id, true)",
            {"organization_id": str(organization_id)},
        ),
        ("SELECT set_config('app.current_org_id', '', true)", None),
        ("SELECT set_config('app.platform_scope', 'false', true)", None),
    ]


class ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class AccessLockSession:
    def __init__(self, membership, grant) -> None:
        self.results = iter((ScalarResult(membership), ScalarResult(grant)))
        self.statements: list[str] = []

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return next(self.results)


@pytest.mark.asyncio
async def test_active_liff_access_locks_user_row() -> None:
    user = SimpleNamespace(id=uuid4(), status="active")
    session = AccessLockSession(user, None)

    result = await AuthenticationRepository(session).lock_user(user.id)  # type: ignore[arg-type]

    assert result is user
    assert len(session.statements) == 1
    assert "FROM users" in session.statements[0]
    assert "FOR UPDATE" in session.statements[0]


@pytest.mark.asyncio
async def test_active_liff_access_locks_active_line_binding() -> None:
    binding = LineUserBinding(line_user_id="U-lock-binding", user_id=uuid4(), status="active")
    session = AccessLockSession(binding, None)

    result = await AuthenticationRepository(session).lock_line_binding("U-lock-binding")  # type: ignore[arg-type]

    assert result is binding
    assert len(session.statements) == 1
    assert "FROM line_user_bindings" in session.statements[0]
    assert "line_user_bindings.status" in session.statements[0]
    assert "FOR UPDATE" in session.statements[0]


@pytest.mark.asyncio
async def test_active_liff_access_locks_exact_grant_then_membership() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    membership = OrganizationMembership(
        id=uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        role="VOLUNTEER",
        status="active",
    )
    grant = VolunteerAccessGrant(
        id=uuid4(),
        membership_id=membership.id,
        user_id=user_id,
        organization_id=organization_id,
        application_id=uuid4(),
        status="active",
    )
    session = AccessLockSession(grant, membership)

    result = await AuthenticationRepository(session).lock_effective_volunteer_access(  # type: ignore[arg-type]
        user_id, organization_id
    )

    assert result == (membership, grant)
    assert len(session.statements) == 2
    assert all("FOR UPDATE" in statement for statement in session.statements)
    grant_statement = session.statements[0]
    assert "volunteer_access_grants.membership_id" in grant_statement
    assert "volunteer_access_grants.user_id" in grant_statement
    assert "volunteer_access_grants.organization_id" in grant_statement
    assert "organization_memberships.id" in session.statements[1]
