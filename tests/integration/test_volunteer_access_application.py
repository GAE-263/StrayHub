from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_access_service import VolunteerAccessService


class _Verifier:
    async def verify(self, token):
        return "Uapplicant"


class _IdentityRepository:
    def __init__(self):
        self.binding = None
        self.users = []

    async def get_line_binding(self, line_user_id):
        return self.binding

    async def get_organization(self, organization_id):
        return SimpleNamespace(id=organization_id, name="收容所 A", status="active")

    async def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        self.users.append(value)
        if value.__class__.__name__ == "LineUserBinding":
            self.binding = value
        return value


class _Repository:
    def __init__(self, *, enabled=True):
        self.organization_id = uuid4()
        self.enabled = enabled
        self.values = []

    async def policy(self):
        return SimpleNamespace(applications_enabled=self.enabled)

    async def pending_application_for_user(self, user_id, *, for_update=False):
        return next(
            (
                value
                for value in self.values
                if value.user_id == user_id and value.status == "pending"
            ),
            None,
        )

    async def applications_for_user(self, user_id, *, limit=50):
        return [value for value in self.values if value.user_id == user_id]

    async def application(self, application_id, *, for_update=False):
        return next((value for value in self.values if value.id == application_id), None)

    async def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        self.values.append(value)
        return value


@pytest.mark.asyncio
async def test_submit_atomically_creates_identity_binding_and_pending_without_membership() -> None:
    repository = _Repository()
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())

    first = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
        now=datetime.now(timezone.utc),
    )
    second = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
        now=datetime.now(timezone.utc),
    )

    assert first.created is True
    assert second.created is False
    assert len(repository.values) == 1
    assert not any(
        value.__class__.__name__ == "OrganizationMembership" for value in identities.users
    )


@pytest.mark.asyncio
async def test_disabled_entry_blocks_new_submit_but_status_remains_available() -> None:
    repository = _Repository(enabled=False)
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())

    with pytest.raises(DomainError, match="暫停接受新申請"):
        await service.submit(
            id_token="token",
            entry_reference_id=uuid4(),
            client_request_id=uuid4(),
            consent_acknowledged=True,
        )

    status = await service.status(id_token="token", entry_reference_id=uuid4())
    assert status.effective_status == "none"


@pytest.mark.asyncio
async def test_withdraw_then_reapply_preserves_history_without_membership() -> None:
    repository = _Repository()
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())
    first = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
    )
    first.status.application.version = 1

    withdrawn = await service.withdraw(
        id_token="token",
        entry_reference_id=uuid4(),
        application_id=first.status.application.id,
        expected_version=1,
    )
    reapplied = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
    )

    assert withdrawn.effective_status == "withdrawn"
    assert reapplied.created is True
    assert len(repository.values) == 2
    assert repository.values[1].previous_application_id == repository.values[0].id


@pytest.mark.asyncio
async def test_disabled_entry_returns_existing_pending_duplicate() -> None:
    repository = _Repository(enabled=True)
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())
    await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
    )
    repository.enabled = False

    replay = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
    )

    assert replay.created is False
    assert replay.status.effective_status == "pending"
