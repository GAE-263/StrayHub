from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api import dependencies
from services.api.app.api.errors import DomainError


class _AuthRepository:
    def __init__(self, *, platform: bool = False, membership_status: str = "active") -> None:
        self.user_id = uuid4()
        self.organization_id = uuid4()
        self.session_id = uuid4()
        self.user = SimpleNamespace(
            id=self.user_id,
            status="active",
            platform_role="PLATFORM_ADMIN" if platform else None,
        )
        self.session = SimpleNamespace(
            id=self.session_id,
            user_id=self.user_id,
            status="active",
            active_organization_id=None if platform else self.organization_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.membership = SimpleNamespace(
            id=uuid4(),
            organization_id=self.organization_id,
            user_id=self.user_id,
            role="STAFF",
            status=membership_status,
        )

    async def get_session(self, _session_id):
        return self.session

    async def get_user(self, _user_id):
        return self.user

    async def get_organization(self, _organization_id):
        return SimpleNamespace(id=self.organization_id, status="active")

    async def get_membership(self, _user_id, _organization_id):
        return self.membership

    async def set_authentication_user_scope(self, _user_id):
        return None


@pytest.mark.asyncio
async def test_request_context_uses_server_session_membership(monkeypatch) -> None:
    repository = _AuthRepository()
    monkeypatch.setattr(dependencies, "AuthenticationRepository", lambda _session: repository)
    monkeypatch.setattr(dependencies, "set_authentication_user_scope", _noop_scope)
    monkeypatch.setattr(dependencies, "set_organization_scope", _noop_scope)

    context = await dependencies._load_request_context(
        object(), authorization=None, session_id=repository.session_id
    )

    assert context.user_id == repository.user_id
    assert context.organization_id == repository.organization_id
    assert context.role == "STAFF"
    assert context.platform_scope is False


@pytest.mark.asyncio
async def test_platform_admin_does_not_need_membership(monkeypatch) -> None:
    repository = _AuthRepository(platform=True)
    monkeypatch.setattr(dependencies, "AuthenticationRepository", lambda _session: repository)
    called = {"platform": False}

    async def set_platform(_session):
        called["platform"] = True

    monkeypatch.setattr(dependencies, "set_platform_scope", set_platform)
    context = await dependencies._load_request_context(
        object(), authorization=None, session_id=repository.session_id
    )

    assert context.role == "PLATFORM_ADMIN"
    assert context.platform_scope is True
    assert called["platform"] is True


@pytest.mark.asyncio
async def test_disabled_membership_is_rejected_immediately(monkeypatch) -> None:
    repository = _AuthRepository(membership_status="disabled")
    monkeypatch.setattr(dependencies, "AuthenticationRepository", lambda _session: repository)
    monkeypatch.setattr(dependencies, "set_authentication_user_scope", _noop_scope)
    monkeypatch.setattr(dependencies, "set_organization_scope", _noop_scope)

    with pytest.raises(DomainError, match="無法存取此收容所資料"):
        await dependencies._load_request_context(
            object(), authorization=None, session_id=repository.session_id
        )


async def _noop_scope(*_args, **_kwargs):
    return None
