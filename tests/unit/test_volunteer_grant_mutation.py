from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_access_service import VolunteerAccessService
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.volunteer_access import VolunteerAccessGrant

NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)


def _records():
    organization_id = uuid4()
    user_id = uuid4()
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization_id,
        user_id=user_id,
        role="VOLUNTEER",
        status="active",
        valid_from=NOW,
        expires_at=NOW + timedelta(days=7),
        access_version=1,
    )
    grant = VolunteerAccessGrant(
        id=uuid4(),
        organization_id=organization_id,
        user_id=user_id,
        membership_id=membership.id,
        application_id=uuid4(),
        status="active",
        valid_from=membership.valid_from,
        expires_at=membership.expires_at,
        approved_at=NOW,
        source_type="manager_approval",
        version=1,
    )
    return organization_id, membership, grant


def _service(organization_id, membership, grant):
    class Repository:
        def __init__(self):
            self.organization_id = organization_id

        async def grant(self, grant_id, *, for_update=False):
            return grant if grant_id == grant.id else None

    class Identities:
        def __init__(self):
            self.cleared = []

        async def get_membership(self, *_args):
            return membership

        async def clear_volunteer_contexts(self, user_id, organization_id):
            self.cleared.append((user_id, organization_id))

        async def get_line_binding_for_user(self, _user_id):
            return None

    identities = Identities()
    return VolunteerAccessService(Repository(), identities, SimpleNamespace()), identities


@pytest.mark.asyncio
async def test_extend_and_shorten_increment_projection_version() -> None:
    organization_id, membership, grant = _records()
    service, _ = _service(organization_id, membership, grant)
    await service.mutate_grant(
        grant_id=grant.id,
        expected_version=1,
        action="update_period",
        actor_user_id=uuid4(),
        valid_from=NOW,
        expires_at=NOW + timedelta(days=14),
        now=NOW,
    )
    assert grant.version == 2
    assert membership.expires_at == NOW + timedelta(days=14)
    assert membership.access_version == 2


@pytest.mark.asyncio
async def test_immediate_expiry_requires_confirmation_and_revocation_reason() -> None:
    organization_id, membership, grant = _records()
    service, identities = _service(organization_id, membership, grant)
    with pytest.raises(DomainError, match="立即失效"):
        await service.mutate_grant(
            grant_id=grant.id,
            expected_version=1,
            action="update_period",
            actor_user_id=uuid4(),
            valid_from=NOW - timedelta(days=1),
            expires_at=NOW - timedelta(seconds=1),
            now=NOW,
        )
    await service.mutate_grant(
        grant_id=grant.id,
        expected_version=1,
        action="revoke",
        actor_user_id=uuid4(),
        reason="排班異動",
        now=NOW,
    )
    assert grant.status == "revoked"
    assert membership.status == "disabled"
    assert identities.cleared == [(grant.user_id, organization_id)]
    with pytest.raises(DomainError, match="不可再修改"):
        await service.mutate_grant(
            grant_id=grant.id,
            expected_version=2,
            action="revoke",
            actor_user_id=uuid4(),
            reason="again",
            now=NOW,
        )
