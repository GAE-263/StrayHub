from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_access_service import VolunteerAccessService
from services.api.app.persistence.models.volunteer_access import VolunteerAccessGrant


@pytest.mark.asyncio
async def test_approving_one_service_date_keeps_other_date_pending() -> None:
    organization_id = uuid4()
    application = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        user_id=uuid4(),
        status="pending",
        version=1,
        applicant_surname="黃",
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

        async def get_organization(self, target_organization_id):
            return SimpleNamespace(
                id=target_organization_id,
                name="收容所 A",
                status="active",
                timezone="Asia/Taipei",
            )

    now = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
    service = VolunteerAccessService(Repository(), Identities(), object())

    decided_application, _, grant = await service.decide_application(
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
    assert decided_application.applicant_surname == "黃"
    assert grant.valid_from == datetime(2026, 8, 24, 16, 0, tzinfo=timezone.utc)
    assert grant.expires_at == datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_two_service_date_approval_notifies_exactly_once_after_final_approval() -> None:
    organization_id = uuid4()
    application = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        user_id=uuid4(),
        status="pending",
        version=1,
        applicant_surname="黃",
        decision_reason=None,
        decided_at=None,
        decided_by_user_id=None,
    )
    requested_dates = {
        requested_date: SimpleNamespace(
            service_date=requested_date,
            status="pending",
            version=1,
            decided_at=None,
            decided_by_user_id=None,
            decision_reason=None,
        )
        for requested_date in (date(2026, 9, 10), date(2026, 9, 11))
    }

    class Repository:
        def __init__(self) -> None:
            self.organization_id = organization_id
            self.grant = None

        async def application(self, application_id, *, for_update=False):
            return application if application_id == application.id else None

        async def service_date_for_application(
            self, application_id, requested_date, *, for_update=False
        ):
            return requested_dates.get(requested_date) if application_id == application.id else None

        async def grant_for_application(self, application_id):
            return self.grant if application_id == application.id else None

        async def policy(self):
            return SimpleNamespace(
                version=1,
                default_grant_duration_hours=168,
                applications_enabled=True,
                insurance_required=False,
            )

        async def add(self, value):
            value.id = getattr(value, "id", None) or uuid4()
            if isinstance(value, VolunteerAccessGrant):
                self.grant = value
            return value

        async def pending_service_date_count(self, application_id):
            assert application_id == application.id
            return sum(item.status == "pending" for item in requested_dates.values())

    class Identities:
        def __init__(self) -> None:
            self.membership = None
            self.binding_id = uuid4()

        async def get_membership(self, user_id, target_organization_id):
            assert user_id == application.user_id
            assert target_organization_id == organization_id
            return self.membership

        async def add(self, value):
            value.id = getattr(value, "id", None) or uuid4()
            self.membership = value
            return value

        async def get_organization(self, target_organization_id):
            assert target_organization_id == organization_id
            return SimpleNamespace(
                id=organization_id,
                name="收容所 A",
                status="active",
                timezone="Asia/Taipei",
            )

        async def get_line_binding_for_user(self, user_id):
            assert user_id == application.user_id
            return SimpleNamespace(id=self.binding_id)

    class Audit:
        def __init__(self) -> None:
            self.events = []

        async def record(self, **event):
            self.events.append(event)

    class Notifications:
        def __init__(self) -> None:
            self.events = []

        async def enqueue(self, **event):
            self.events.append(event)

    repository = Repository()
    identities = Identities()
    audit = Audit()
    notifications = Notifications()
    service = VolunteerAccessService(
        repository,
        identities,
        object(),
        audit=audit,
        notifications=notifications,
    )
    first_date, final_date = requested_dates
    now = datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc)

    first_result, membership, grant = await service.decide_application(
        application_id=application.id,
        expected_version=1,
        decision="approve",
        actor_user_id=uuid4(),
        service_date=first_date,
        now=now,
    )

    assert first_result.status == "pending"
    assert membership is identities.membership
    assert grant is repository.grant
    assert requested_dates[first_date].status == "approved"
    assert requested_dates[final_date].status == "pending"
    assert [event["action"] for event in audit.events] == ["volunteer_application.pending"]
    assert notifications.events == []

    final_result, final_membership, final_grant = await service.decide_application(
        application_id=application.id,
        expected_version=2,
        decision="approve",
        actor_user_id=uuid4(),
        service_date=final_date,
        now=now,
    )

    assert final_result.status == "approved"
    assert final_result.version == 3
    assert final_result.applicant_surname is None
    assert final_membership is membership
    assert final_grant is grant
    assert all(item.status == "approved" for item in requested_dates.values())
    assert [event["action"] for event in audit.events] == [
        "volunteer_application.pending",
        "volunteer_application.approved",
    ]
    assert len(notifications.events) == 1
    assert notifications.events[0]["event_type"] == "approved"
    assert notifications.events[0]["resource_version"] == 3
    assert notifications.events[0]["payload"]["application_status"] == "approved"


@pytest.mark.asyncio
async def test_rejecting_the_last_service_date_rejects_the_application() -> None:
    target_organization_id = uuid4()
    application = SimpleNamespace(
        id=uuid4(),
        organization_id=target_organization_id,
        user_id=uuid4(),
        status="pending",
        version=1,
        applicant_surname="黃",
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
    assert decided_application.applicant_surname is None


@pytest.mark.asyncio
async def test_active_platform_restriction_blocks_backend_approval() -> None:
    organization_id = uuid4()
    application = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        user_id=uuid4(),
        status="pending",
        version=1,
        applicant_surname="黃",
        decision_reason=None,
        decided_at=None,
        decided_by_user_id=None,
    )

    class Repository:
        async def application(self, application_id, *, for_update=False):
            return application if application_id == application.id else None

    Repository.organization_id = organization_id

    class SummaryRepository:
        async def has_active_platform_restriction(self, user_id):
            assert user_id == application.user_id
            return True

    service = VolunteerAccessService(
        Repository(), object(), object(), summary_repository=SummaryRepository()
    )
    with pytest.raises(DomainError) as error:
        await service.decide_application(
            application_id=application.id,
            expected_version=1,
            decision="approve",
            actor_user_id=uuid4(),
            valid_from=datetime.now(timezone.utc),
        )
    assert error.value.code == "active_platform_restriction"


@pytest.mark.asyncio
async def test_policy_change_preserves_old_grant_and_applies_to_future_approval() -> None:
    organization_id = uuid4()
    user_id = uuid4()
    applications = {
        service_date: SimpleNamespace(
            id=uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            status="pending",
            version=1,
            applicant_surname="黃",
            decision_reason=None,
            decided_at=None,
            decided_by_user_id=None,
        )
        for service_date in (date(2026, 9, 10), date(2026, 9, 20))
    }
    requested_dates = {
        service_date: SimpleNamespace(
            service_date=service_date,
            status="pending",
            version=1,
            decided_at=None,
            decided_by_user_id=None,
            decision_reason=None,
        )
        for service_date in applications
    }
    policy = SimpleNamespace(version=1, default_grant_duration_hours=168)
    grants: dict = {}

    class Repository:
        def __init__(self) -> None:
            self.organization_id = organization_id

        async def application(self, application_id, *, for_update=False):
            return next(
                (item for item in applications.values() if item.id == application_id),
                None,
            )

        async def service_date_for_application(
            self, application_id, selected_service_date, *, for_update=False
        ):
            application = applications[selected_service_date]
            return (
                requested_dates[selected_service_date] if application.id == application_id else None
            )

        async def grant_for_application(self, application_id):
            return grants.get(application_id)

        async def policy(self):
            return policy

        async def add(self, value):
            value.id = getattr(value, "id", None) or uuid4()
            if isinstance(value, VolunteerAccessGrant):
                grants[value.application_id] = value
            return value

        async def pending_service_date_count(self, application_id):
            return 0

    class Identities:
        membership = None
        profile_surnames = []

        async def get_membership(self, user_id, target_organization_id):
            return self.membership

        async def add(self, value):
            value.id = getattr(value, "id", None) or uuid4()
            self.membership = value
            return value

        async def get_organization(self, target_organization_id):
            return SimpleNamespace(
                id=target_organization_id,
                name="收容所 A",
                status="active",
                timezone="Asia/Taipei",
            )

        async def upsert_volunteer_profile(self, user_id, *, surname):
            self.profile_surnames.append((user_id, surname))
            return SimpleNamespace(user_id=user_id, surname=surname)

    identities = Identities()
    service = VolunteerAccessService(Repository(), identities, object())
    first_date, second_date = applications
    _, _, old_grant = await service.decide_application(
        application_id=applications[first_date].id,
        expected_version=1,
        decision="approve",
        actor_user_id=uuid4(),
        service_date=first_date,
        now=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )
    old_expiry = old_grant.expires_at

    policy.version = 2
    policy.default_grant_duration_hours = 336
    _, _, new_grant = await service.decide_application(
        application_id=applications[second_date].id,
        expected_version=1,
        decision="approve",
        actor_user_id=uuid4(),
        service_date=second_date,
        now=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )

    assert old_grant.expires_at == old_expiry == datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)
    assert applications[first_date].applicant_surname is None
    assert new_grant.valid_from == datetime(2026, 9, 19, 16, 0, tzinfo=timezone.utc)
    assert new_grant.expires_at == datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    assert new_grant.duration_hours_used == 336
    assert identities.profile_surnames == [(user_id, "黃"), (user_id, "黃")]
