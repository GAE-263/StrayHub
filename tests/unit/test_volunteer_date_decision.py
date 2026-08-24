from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.volunteer_access_service import VolunteerAccessService


@pytest.mark.asyncio
async def test_approving_one_service_date_keeps_other_date_pending() -> None:
    organization_id = uuid4()
    application = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        user_id=uuid4(),
        status="pending",
        version=1,
        decision_reason=None,
        decided_at=None,
        decided_by_user_id=None,
    )
    selected_date = SimpleNamespace(
        service_date=date(2026, 8, 25),
        status="pending",
        version=1,
        decided_at=None,
        decided_by_user_id=None,
        decision_reason=None,
    )
    other_date = SimpleNamespace(
        service_date=date(2026, 8, 26),
        status="pending",
        version=1,
    )

    class Repository:
        def __init__(self) -> None:
            self.organization_id = organization_id

        async def application(self, application_id, *, for_update=False):
            return application if application_id == application.id else None

        async def service_date_for_application(
            self, application_id, service_date, *, for_update=False
        ):
            if application_id == application.id and service_date == selected_date.service_date:
                return selected_date
            return None

        async def grant_for_application(self, application_id):
            return None

        async def policy(self):
            return SimpleNamespace(version=1, default_grant_duration_hours=168)

        async def add(self, value):
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            return value

        async def pending_service_date_count(self, application_id):
            return int(other_date.status == "pending")

    class Identities:
        async def get_membership(self, user_id, target_organization_id):
            return None

        async def add(self, value):
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            return value

    now = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
    service = VolunteerAccessService(Repository(), Identities(), object())

    decided_application, _, _ = await service.decide_application(
        application_id=application.id,
        expected_version=1,
        decision="approve",
        actor_user_id=uuid4(),
        service_date=selected_date.service_date,
        now=now,
    )

    assert selected_date.status == "approved"
    assert other_date.status == "pending"
    assert decided_application.status == "pending"


@pytest.mark.asyncio
async def test_rejecting_the_last_service_date_rejects_the_application() -> None:
    target_organization_id = uuid4()
    application = SimpleNamespace(
        id=uuid4(),
        organization_id=target_organization_id,
        user_id=uuid4(),
        status="pending",
        version=1,
        decision_reason=None,
        decided_at=None,
        decided_by_user_id=None,
    )
    selected_date = SimpleNamespace(
        service_date=date(2026, 8, 25),
        status="pending",
        version=1,
        decided_at=None,
        decided_by_user_id=None,
        decision_reason=None,
    )

    class Repository:
        organization_id = target_organization_id

        async def application(self, application_id, *, for_update=False):
            return application if application_id == application.id else None

        async def service_date_for_application(
            self, application_id, service_date, *, for_update=False
        ):
            return selected_date

        async def grant_for_application(self, application_id):
            return None

        async def pending_service_date_count(self, application_id):
            return 0

    service = VolunteerAccessService(Repository(), object(), object())
    decided_application, _, _ = await service.decide_application(
        application_id=application.id,
        expected_version=1,
        decision="reject",
        reason="名額已滿",
        actor_user_id=uuid4(),
        service_date=selected_date.service_date,
        now=datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc),
    )

    assert selected_date.status == "rejected"
    assert decided_application.status == "rejected"
