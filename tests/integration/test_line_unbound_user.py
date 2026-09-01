from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_webhook_session import LineWebhookSessionService


class Identity:
    def __init__(self, binding=None, sessions=None):
        self._binding = binding
        self._sessions = sessions or []
        self.added = []

    async def binding(self, _line_user_id):
        return self._binding

    async def sessions(self, _user_id):
        return self._sessions

    async def add(self, value):
        self.added.append(value)
        return value


class Auth:
    def __init__(self, user, memberships, organization):
        self.user = user
        self._memberships = memberships
        self.organization = organization

    async def get_user(self, _user_id):
        return self.user

    async def memberships(self, _user_id, *, active_only=False):
        return self._memberships

    async def get_organization(self, _organization_id):
        return self.organization


@pytest.mark.asyncio
async def test_unbound_line_identity_requires_liff_without_creating_session() -> None:
    identity = Identity()
    auth = Auth(None, [], None)
    service = LineWebhookSessionService(identity, auth)
    with pytest.raises(DomainError, match="LINE 身分綁定"):
        await service.resolve("line-user")
    assert identity.added == []


@pytest.mark.asyncio
async def test_multiple_memberships_require_explicit_shelter_context() -> None:
    user_id = uuid4()
    binding = SimpleNamespace(user_id=user_id)
    memberships = [
        SimpleNamespace(organization_id=uuid4(), status="active"),
        SimpleNamespace(organization_id=uuid4(), status="active"),
    ]
    service = LineWebhookSessionService(
        Identity(binding=binding),
        Auth(SimpleNamespace(id=user_id, status="active"), memberships, None),
    )
    with pytest.raises(DomainError, match="明確選擇收容所"):
        await service.resolve("line-user")


@pytest.mark.asyncio
async def test_selected_webhook_session_resolves_exact_membership() -> None:
    user_id = uuid4()
    organization_a = uuid4()
    organization_b = uuid4()
    binding = SimpleNamespace(user_id=user_id)
    memberships = [
        SimpleNamespace(organization_id=organization_a, status="active"),
        SimpleNamespace(organization_id=organization_b, status="active"),
    ]
    selected = SimpleNamespace(organization_id=organization_b)
    organization = SimpleNamespace(id=organization_b, status="active")
    service = LineWebhookSessionService(
        Identity(binding=binding, sessions=[selected]),
        Auth(SimpleNamespace(id=user_id, status="active"), memberships, organization),
    )

    assert await service.resolve("line-user") is selected
