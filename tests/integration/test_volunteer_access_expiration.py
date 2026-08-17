from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.volunteer_expiration_service import (
    VolunteerExpirationService,
)


@pytest.mark.asyncio
async def test_expiration_sweep_is_idempotent_and_clears_only_target_context() -> None:
    now = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    membership = SimpleNamespace(id=uuid4(), status="active", access_version=1)
    grant = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        user_id=uuid4(),
        membership_id=membership.id,
        status="active",
        valid_from=now - timedelta(days=7),
        expires_at=now,
        version=1,
    )

    class Repository:
        def __init__(self):
            self.organization_id = organization_id

        async def due_or_invalid_grants(self, **_kwargs):
            return [grant] if grant.status == "active" else []

    class Identities:
        def __init__(self):
            self.cleared = []

        async def get_membership(self, *_args):
            return membership

        async def clear_volunteer_contexts(self, user_id, target):
            self.cleared.append((user_id, target))

        async def get_line_binding_for_user(self, _user_id):
            return None

    identities = Identities()
    service = VolunteerExpirationService(Repository(), identities)
    assert await service.sweep(now=now) == 1
    assert await service.sweep(now=now) == 0
    assert grant.status == "expired"
    assert membership.status == "disabled"
    assert identities.cleared == [(grant.user_id, organization_id)]
