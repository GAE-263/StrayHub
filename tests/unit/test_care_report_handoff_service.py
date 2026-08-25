from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import issue_animal_confirmation_token
from services.api.app.application.care_report_handoff_service import CareReportHandoffService


class HandoffRepository:
    def __init__(self, organization_id):
        self.organization_id = organization_id
        self.rows = []

    async def replace_pending(self, handoff, *, now):
        for row in self.rows:
            if row.user_id == handoff.user_id and row.status == "pending":
                row.status = "superseded"
                row.superseded_at = now
        self.rows.append(handoff)
        return handoff

    async def lock_pending_for_user(self, user_id):
        return next(
            (
                row
                for row in reversed(self.rows)
                if row.organization_id == self.organization_id
                and row.user_id == user_id
                and row.status == "pending"
            ),
            None,
        )

    async def latest_for_user(self, user_id):
        return next(
            (
                row
                for row in reversed(self.rows)
                if row.organization_id == self.organization_id and row.user_id == user_id
            ),
            None,
        )

    async def flush(self):
        return None


class Authentication:
    def __init__(self, *, user, organization, membership, grant):
        self.user = user
        self.organization = organization
        self.membership = membership
        self.grant = grant

    async def get_user(self, user_id):
        return self.user if self.user.id == user_id else None

    async def get_organization(self, organization_id):
        return self.organization if self.organization.id == organization_id else None

    async def lock_effective_volunteer_access(self, user_id, organization_id):
        if self.grant is None or self.user.id != user_id or self.organization.id != organization_id:
            return None
        return self.membership, self.grant


class Animals:
    def __init__(self, animal):
        self.animal = animal

    async def get(self, animal_id):
        return self.animal if self.animal.id == animal_id else None


class Scopes:
    def __init__(self, allowed=True):
        self.allowed = allowed

    async def is_animal_reportable(self, **_kwargs):
        return self.allowed


@pytest.fixture
def handoff_fixture(monkeypatch):
    monkeypatch.setenv("ANIMAL_CONFIRMATION_SECRET", "handoff-unit-test-secret")
    now = datetime.now(timezone.utc)
    user_id = uuid4()
    organization_id = uuid4()
    membership_id = uuid4()
    animal_id = uuid4()
    session_id = uuid4()
    user = SimpleNamespace(id=user_id, status="active")
    organization = SimpleNamespace(id=organization_id, status="active")
    membership = SimpleNamespace(
        id=membership_id,
        organization_id=organization_id,
        user_id=user_id,
        role="VOLUNTEER",
        status="active",
    )
    grant = SimpleNamespace(
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        status="active",
    )
    animal = SimpleNamespace(id=animal_id, organization_id=organization_id, status="active")
    repository = HandoffRepository(organization_id)
    authentication = Authentication(
        user=user,
        organization=organization,
        membership=membership,
        grant=grant,
    )
    animals = Animals(animal)
    scopes = Scopes()
    service = CareReportHandoffService(
        repository,
        authentication=authentication,
        animals=animals,
        reportable_scopes=scopes,
        clock=lambda: now,
    )
    token = issue_animal_confirmation_token(
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        session_id=session_id,
        animal_id=animal_id,
    )
    return SimpleNamespace(
        now=now,
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        animal_id=animal_id,
        session_id=session_id,
        animal=animal,
        authentication=authentication,
        repository=repository,
        service=service,
        token=token,
    )


async def _create(fixture, *, source="liff_scan"):
    return await fixture.service.create_or_replace_handoff(
        user_id=fixture.user_id,
        organization_id=fixture.organization_id,
        membership_id=fixture.membership_id,
        session_id=fixture.session_id,
        animal_id=fixture.animal_id,
        confirmation_token=fixture.token,
        source=source,
    )


@pytest.mark.asyncio
async def test_create_sets_pending_handoff_and_fixed_fifteen_minute_ttl(handoff_fixture) -> None:
    handoff = await _create(handoff_fixture)

    assert handoff.status == "pending"
    assert handoff.expires_at == handoff_fixture.now + timedelta(minutes=15)
    assert handoff.user_id == handoff_fixture.user_id
    assert handoff.membership_id == handoff_fixture.membership_id
    assert handoff.animal_id == handoff_fixture.animal_id
    assert handoff.source == "liff_scan"


@pytest.mark.asyncio
async def test_second_animal_supersedes_first_pending_handoff(handoff_fixture) -> None:
    first = await _create(handoff_fixture)
    second_animal_id = uuid4()
    handoff_fixture.animal.id = second_animal_id
    handoff_fixture.animal_id = second_animal_id
    handoff_fixture.token = issue_animal_confirmation_token(
        user_id=handoff_fixture.user_id,
        organization_id=handoff_fixture.organization_id,
        membership_id=handoff_fixture.membership_id,
        session_id=handoff_fixture.session_id,
        animal_id=second_animal_id,
    )

    second = await _create(handoff_fixture, source="qr_deeplink")

    assert first.status == "superseded"
    assert first.superseded_at == handoff_fixture.now
    assert second.status == "pending"
    assert second.animal_id == second_animal_id


@pytest.mark.asyncio
async def test_handoff_can_be_consumed_only_once(handoff_fixture) -> None:
    await _create(handoff_fixture)

    consumed = await handoff_fixture.service.consume_pending_handoff(
        user_id=handoff_fixture.user_id,
        organization_id=handoff_fixture.organization_id,
    )

    assert consumed.status == "consumed"
    assert consumed.consumed_at == handoff_fixture.now
    with pytest.raises(DomainError) as error:
        await handoff_fixture.service.consume_pending_handoff(
            user_id=handoff_fixture.user_id,
            organization_id=handoff_fixture.organization_id,
        )
    assert error.value.code == "handoff_already_consumed"


@pytest.mark.asyncio
async def test_expired_handoff_cannot_be_consumed(handoff_fixture) -> None:
    handoff = await _create(handoff_fixture)
    handoff.expires_at = handoff_fixture.now

    with pytest.raises(DomainError) as error:
        await handoff_fixture.service.consume_pending_handoff(
            user_id=handoff_fixture.user_id,
            organization_id=handoff_fixture.organization_id,
        )

    assert error.value.code == "handoff_expired"
    assert handoff.status == "expired"


@pytest.mark.asyncio
async def test_revoked_grant_rejects_consume(handoff_fixture) -> None:
    await _create(handoff_fixture)
    handoff_fixture.authentication.grant = None

    with pytest.raises(DomainError) as error:
        await handoff_fixture.service.consume_pending_handoff(
            user_id=handoff_fixture.user_id,
            organization_id=handoff_fixture.organization_id,
        )

    assert error.value.code == "authorization_no_longer_valid"


@pytest.mark.asyncio
async def test_inactive_animal_rejects_consume(handoff_fixture) -> None:
    await _create(handoff_fixture)
    handoff_fixture.animal.status = "inactive"

    with pytest.raises(DomainError) as error:
        await handoff_fixture.service.consume_pending_handoff(
            user_id=handoff_fixture.user_id,
            organization_id=handoff_fixture.organization_id,
        )

    assert error.value.code == "animal_no_longer_available"


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["wrong_user", "wrong_organization"])
async def test_wrong_user_or_tenant_cannot_consume(handoff_fixture, identity) -> None:
    await _create(handoff_fixture)

    with pytest.raises(DomainError) as error:
        await handoff_fixture.service.consume_pending_handoff(
            user_id=uuid4() if identity == "wrong_user" else handoff_fixture.user_id,
            organization_id=(
                uuid4() if identity == "wrong_organization" else handoff_fixture.organization_id
            ),
        )

    assert error.value.code == "no_pending_handoff"


def test_consume_signature_does_not_accept_animal_or_handoff_identifier() -> None:
    parameters = inspect.signature(CareReportHandoffService.consume_pending_handoff).parameters

    assert set(parameters) == {"self", "user_id", "organization_id"}
