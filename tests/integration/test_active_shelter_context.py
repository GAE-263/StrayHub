from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.context_service import ActiveShelterContextService
from services.api.app.persistence.models.identity import Organization, SessionRecord, User


@pytest.mark.asyncio
async def test_context_switch_requires_explicit_active_membership():
    user = User(id=uuid4(), username="u", display_name="U", status="active")
    org = Organization(id=uuid4(), code="CTX", name="Context", status="active")
    session = SessionRecord(
        id=uuid4(),
        user_id=user.id,
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    class Repository:
        async def get_session(self, value):
            return session if value == session.id else None

        async def get_user(self, value):
            return user if value == user.id else None

        async def get_organization(self, value):
            return org if value == org.id else None

        async def get_membership(self, user_id, organization_id):
            return None

    with pytest.raises(DomainError, match="無法存取"):
        await ActiveShelterContextService(Repository()).switch(
            session_id=session.id, organization_id=org.id
        )


@pytest.mark.asyncio
async def test_future_or_expired_volunteer_cannot_establish_context() -> None:
    user = User(id=uuid4(), username="volunteer", display_name="V", status="active")
    org = Organization(id=uuid4(), code="CTX-V", name="Context V", status="active")
    session = SessionRecord(
        id=uuid4(),
        user_id=user.id,
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    class Repository:
        async def get_session(self, _value):
            return session

        async def get_user(self, _value):
            return user

        async def get_organization(self, _value):
            return org

        async def get_effective_membership(self, _user_id, _organization_id):
            return None

    with pytest.raises(DomainError, match="無法存取"):
        await ActiveShelterContextService(Repository()).switch(
            session_id=session.id, organization_id=org.id
        )
