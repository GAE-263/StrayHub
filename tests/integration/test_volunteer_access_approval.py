from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.volunteer_access_service import VolunteerAccessService
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerAccessGrant,
    VolunteerApplication,
)


@pytest.mark.asyncio
async def test_approval_atomically_projects_finite_membership_grant_and_outbox() -> None:
    now = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
    organization_id = uuid4()
    user_id = uuid4()
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=organization_id,
        user_id=user_id,
        status="pending",
        version=1,
        submitted_at=now - timedelta(hours=1),
    )
    policy = OrganizationVolunteerAccessPolicy(
        organization_id=organization_id,
        default_grant_duration_hours=72,
        applications_enabled=True,
        version=3,
    )

    class Repository:
        def __init__(self):
            self.organization_id = organization_id
            self.values = []

        async def application(self, application_id, *, for_update=False):
            return application if application_id == application.id else None

        async def policy(self, *, for_update=False):
            return policy

        async def add(self, value):
            value.id = getattr(value, "id", None) or uuid4()
            self.values.append(value)
            return value

    class Identities:
        def __init__(self):
            self.membership = None

        async def get_membership(self, *_args):
            return self.membership

        async def add(self, value):
            value.id = getattr(value, "id", None) or uuid4()
            self.membership = value
            return value

        async def get_line_binding_for_user(self, _user_id):
            return SimpleNamespace(id=uuid4())

        async def get_organization(self, _organization_id):
            return SimpleNamespace(id=organization_id, name="收容所 A", status="active")

    class Notifications:
        def __init__(self):
            self.events = []

        async def enqueue(self, **event):
            self.events.append(event)

    repository = Repository()
    identities = Identities()
    notifications = Notifications()
    approved, membership, grant = await VolunteerAccessService(
        repository,
        identities,
        SimpleNamespace(),
        notifications=notifications,
    ).decide_application(
        application_id=application.id,
        expected_version=1,
        decision="approve",
        actor_user_id=uuid4(),
        now=now,
    )

    assert approved.status == "approved"
    assert isinstance(membership, OrganizationMembership)
    assert isinstance(grant, VolunteerAccessGrant)
    assert membership.valid_from == grant.valid_from == now
    assert membership.expires_at == grant.expires_at == now + timedelta(hours=72)
    assert grant.policy_version_used == 3
    assert grant.duration_hours_used == 72
    assert notifications.events[0]["event_type"] == "approved"
    assert notifications.events[0]["line_binding_id"] is not None
