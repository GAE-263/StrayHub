from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api import volunteer_access as api


class _Verifier:
    async def verify(self, token: str) -> str:
        assert token == "synthetic-token"
        return "Uverified-line-user"


@pytest.mark.asyncio
async def test_self_status_returns_empty_without_creating_a_line_identity(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _Identities:
        def __init__(self, _session) -> None:
            pass

        async def get_line_binding(self, line_user_id: str):
            assert line_user_id == "Uverified-line-user"
            return None

    async def forbidden_scope(*_args, **_kwargs) -> None:
        raise AssertionError("an unbound identity must not enumerate organizations")

    monkeypatch.setattr(api, "AuthenticationRepository", _Identities)
    monkeypatch.setattr(api, "set_platform_scope", forbidden_scope)
    caplog.set_level(logging.INFO, logger=api.__name__)

    response = await api.list_own_volunteer_application_statuses(
        api.VolunteerOwnStatusRequest(id_token="synthetic-token"),
        object(),
        _Verifier(),
    )

    assert response.items == []
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "[volunteer-status] request organization_filter_present=false" in messages
    assert "authenticated user_resolved=false" in messages
    assert "response_200 applications=0" in messages
    assert "synthetic-token" not in messages
    assert "Uverified-line-user" not in messages


@pytest.mark.asyncio
async def test_self_status_reads_each_organization_with_existing_scope_and_user_filter(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user_id = uuid4()
    org_a = uuid4()
    org_b = uuid4()
    now = datetime.now(timezone.utc)
    applications = {
        org_a: SimpleNamespace(
            id=uuid4(),
            organization_id=org_a,
            user_id=user_id,
            status="pending",
            submitted_at=now,
            decided_at=None,
            decision_reason=None,
            version=1,
        ),
        org_b: SimpleNamespace(
            id=uuid4(),
            organization_id=org_b,
            user_id=user_id,
            status="approved",
            submitted_at=now - timedelta(days=1),
            decided_at=now,
            decision_reason=None,
            version=2,
        ),
    }
    grant = SimpleNamespace(
        id=uuid4(),
        status="active",
        source_type="manager_approval",
        policy_version_used=1,
        duration_hours_used=24,
        valid_from=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=23),
        version=1,
    )
    scope_events: list[tuple[str, object | None]] = []
    requested_users = []

    class _Identities:
        def __init__(self, _session) -> None:
            pass

        async def get_line_binding(self, _line_user_id: str):
            return SimpleNamespace(user_id=user_id)

    class _Organizations:
        def __init__(self, _session) -> None:
            pass

        async def list(self):
            return [
                SimpleNamespace(id=org_a, name="Shelter A", address=None),
                SimpleNamespace(id=org_b, name="Shelter B", address="New Taipei"),
            ]

    class _Repository:
        def __init__(self, _session, organization_id) -> None:
            self.organization_id = organization_id

        async def applications_for_user(self, received_user_id, *, limit):
            requested_users.append((self.organization_id, received_user_id, limit))
            return [applications[self.organization_id]]

        async def application_detail(self, application_id):
            application = applications[self.organization_id]
            assert application_id == application.id
            return application, [
                SimpleNamespace(
                    service_date=date(2026, 9, 1),
                    status=application.status,
                    decided_at=application.decided_at,
                    decision_reason=None,
                    version=1,
                )
            ]

        async def grant_for_application(self, _application_id):
            return grant if self.organization_id == org_b else None

    async def platform_scope(_session) -> None:
        scope_events.append(("platform", None))

    async def organization_scope(_session, organization_id) -> None:
        scope_events.append(("organization", organization_id))

    monkeypatch.setattr(api, "AuthenticationRepository", _Identities)
    monkeypatch.setattr(api, "OrganizationRepository", _Organizations)
    monkeypatch.setattr(api, "VolunteerAccessRepository", _Repository)
    monkeypatch.setattr(api, "set_platform_scope", platform_scope)
    monkeypatch.setattr(api, "set_organization_scope", organization_scope)
    caplog.set_level(logging.INFO, logger=api.__name__)

    response = await api.list_own_volunteer_application_statuses(
        api.VolunteerOwnStatusRequest(id_token="synthetic-token"),
        object(),
        _Verifier(),
    )

    assert [item.organization.name for item in response.items] == ["Shelter A", "Shelter B"]
    assert response.items[0].effective_status == "pending"
    assert response.items[0].grant is None
    assert response.items[1].effective_status == "active"
    assert response.items[1].grant is not None
    assert scope_events == [
        ("platform", None),
        ("organization", org_a),
        ("organization", org_b),
    ]
    assert requested_users == [(org_a, user_id, 5), (org_b, user_id, 5)]
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "authenticated user_resolved=true" in messages
    assert "response_200 applications=2 pending=1 approved=1" in messages
    assert str(user_id) not in messages
    assert str(org_a) not in messages
    assert str(org_b) not in messages


@pytest.mark.asyncio
async def test_self_status_returns_only_the_five_most_recent_applications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    organization_id = uuid4()
    now = datetime.now(timezone.utc)
    applications = [
        SimpleNamespace(
            id=uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            status="pending",
            submitted_at=now - timedelta(days=offset),
            decided_at=None,
            decision_reason=None,
            version=1,
        )
        for offset in range(7)
    ]

    class _Identities:
        def __init__(self, _session) -> None:
            pass

        async def get_line_binding(self, _line_user_id: str):
            return SimpleNamespace(user_id=user_id)

    class _Organizations:
        def __init__(self, _session) -> None:
            pass

        async def list(self):
            return [SimpleNamespace(id=organization_id, name="Shelter", address=None)]

    class _Repository:
        def __init__(self, _session, received_organization_id) -> None:
            assert received_organization_id == organization_id

        async def applications_for_user(self, received_user_id, *, limit):
            assert received_user_id == user_id
            assert limit == 5
            # Return more than requested to verify the endpoint's global cap too.
            return list(reversed(applications))

        async def application_detail(self, application_id):
            application = next(item for item in applications if item.id == application_id)
            return application, []

        async def grant_for_application(self, _application_id):
            return None

    async def noop_scope(*_args, **_kwargs) -> None:
        pass

    monkeypatch.setattr(api, "AuthenticationRepository", _Identities)
    monkeypatch.setattr(api, "OrganizationRepository", _Organizations)
    monkeypatch.setattr(api, "VolunteerAccessRepository", _Repository)
    monkeypatch.setattr(api, "set_platform_scope", noop_scope)
    monkeypatch.setattr(api, "set_organization_scope", noop_scope)

    response = await api.list_own_volunteer_application_statuses(
        api.VolunteerOwnStatusRequest(id_token="synthetic-token"),
        object(),
        _Verifier(),
    )

    assert len(response.items) == 5
    assert [item.application.id for item in response.items] == [
        application.id for application in applications[:5]
    ]
