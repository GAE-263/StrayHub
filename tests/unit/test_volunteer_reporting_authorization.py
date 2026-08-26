from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)


class Authentication:
    def __init__(self, user, organization, access):
        self.user = user
        self.organization = organization
        self.access = access

    async def get_user(self, user_id):
        return self.user if self.user.id == user_id else None

    async def get_organization(self, organization_id):
        return self.organization if self.organization.id == organization_id else None

    async def lock_effective_volunteer_access(self, user_id, organization_id):
        if self.user.id != user_id or self.organization.id != organization_id:
            return None
        return self.access


class Animals:
    def __init__(self, animal):
        self.animal = animal

    async def get(self, animal_id):
        return self.animal if self.animal is not None and self.animal.id == animal_id else None


@pytest.fixture
def authorization_fixture():
    user_id = uuid4()
    organization_id = uuid4()
    membership_id = uuid4()
    animal_id = uuid4()
    user = SimpleNamespace(id=user_id, status="active")
    organization = SimpleNamespace(id=organization_id, status="active")
    membership = SimpleNamespace(
        id=membership_id,
        user_id=user_id,
        organization_id=organization_id,
        role="VOLUNTEER",
        status="active",
    )
    grant = SimpleNamespace(
        membership_id=membership_id,
        user_id=user_id,
        organization_id=organization_id,
        status="active",
    )
    animal = SimpleNamespace(
        id=animal_id,
        organization_id=organization_id,
        status="active",
    )
    authentication = Authentication(user, organization, (membership, grant))
    service = VolunteerReportingAuthorizationService(authentication, Animals(animal))
    return SimpleNamespace(
        user=user,
        organization=organization,
        membership=membership,
        grant=grant,
        animal=animal,
        authentication=authentication,
        service=service,
    )


@pytest.mark.asyncio
async def test_authorizes_effective_volunteer_and_active_tenant_animal(
    authorization_fixture,
) -> None:
    fixture = authorization_fixture

    result = await fixture.service.authorize(
        user_id=fixture.user.id,
        organization_id=fixture.organization.id,
        membership_id=fixture.membership.id,
        animal_id=fixture.animal.id,
    )

    assert result.membership is fixture.membership
    assert result.grant is fixture.grant
    assert result.animal is fixture.animal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition",
    [
        "inactive_user",
        "inactive_org",
        "expired_membership",
        "expired_grant",
        "revoked_grant",
    ],
)
async def test_denies_inactive_or_expired_volunteer_access(
    authorization_fixture, condition
) -> None:
    fixture = authorization_fixture
    if condition == "inactive_user":
        fixture.user.status = "inactive"
    elif condition == "inactive_org":
        fixture.organization.status = "inactive"
    else:
        # The repository returns no access for expired memberships or expired/revoked grants.
        fixture.authentication.access = None

    with pytest.raises(DomainError) as error:
        await fixture.service.authorize(
            user_id=fixture.user.id,
            organization_id=fixture.organization.id,
            membership_id=fixture.membership.id,
        )

    assert error.value.code == "authorization_no_longer_valid"


@pytest.mark.asyncio
async def test_denies_membership_mismatch(authorization_fixture) -> None:
    fixture = authorization_fixture

    with pytest.raises(DomainError) as error:
        await fixture.service.authorize(
            user_id=fixture.user.id,
            organization_id=fixture.organization.id,
            membership_id=uuid4(),
        )

    assert error.value.code == "authorization_no_longer_valid"


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["inactive", "foreign", "missing"])
async def test_denies_unavailable_animal(authorization_fixture, condition) -> None:
    fixture = authorization_fixture
    if condition == "inactive":
        fixture.animal.status = "inactive"
    elif condition == "foreign":
        fixture.animal.organization_id = uuid4()
    else:
        fixture.service.animals.animal = None

    with pytest.raises(DomainError) as error:
        await fixture.service.authorize(
            user_id=fixture.user.id,
            organization_id=fixture.organization.id,
            membership_id=fixture.membership.id,
            animal_id=fixture.animal.id,
        )

    assert error.value.code == "animal_no_longer_available"
    assert error.value.status_code == 404
