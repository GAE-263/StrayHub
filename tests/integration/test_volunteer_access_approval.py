import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_access_service import VolunteerAccessService
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerAccessGrant,
    VolunteerApplication,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


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
        valid_from=now,
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


async def _seed_pending_application(
    connection,
    *,
    organization_id,
    user_id,
    actor_user_id,
    application_id,
    now,
):
    suffix = organization_id.hex[:12]
    await connection.execute(
        """INSERT INTO organizations (id, name, code, status, created_at, updated_at)
           VALUES ($1, $2, $3, 'active', $4, $4)""",
        organization_id,
        f"Approval shelter {suffix}",
        f"approval-{suffix}",
        now,
    )
    await connection.executemany(
        """INSERT INTO users (id, display_name, status, created_at, updated_at)
           VALUES ($1, $2, 'active', $3, $3)""",
        [(user_id, "Approval volunteer", now), (actor_user_id, "Approval manager", now)],
    )
    await connection.execute(
        """INSERT INTO organization_volunteer_access_policies
           (organization_id, applications_enabled, default_grant_duration_hours, version,
            created_at, updated_at)
           VALUES ($1, true, 72, 1, $2, $2)""",
        organization_id,
        now,
    )
    await connection.execute(
        """INSERT INTO volunteer_applications
           (id, organization_id, user_id, status, submitted_at, version, created_at, updated_at)
           VALUES ($1, $2, $3, 'pending', $4, 1, $4, $4)""",
        application_id,
        organization_id,
        user_id,
        now - timedelta(hours=1),
    )


async def _cleanup_approval_fixture(connection, *, organization_ids, user_ids):
    await connection.execute(
        "DELETE FROM volunteer_decision_batch_items WHERE organization_id = ANY($1::uuid[])",
        organization_ids,
    )
    await connection.execute(
        "DELETE FROM volunteer_decision_batches WHERE organization_id = ANY($1::uuid[])",
        organization_ids,
    )
    await connection.execute(
        "DELETE FROM volunteer_access_grants WHERE organization_id = ANY($1::uuid[])",
        organization_ids,
    )
    await connection.execute(
        "DELETE FROM volunteer_application_service_dates WHERE organization_id = ANY($1::uuid[])",
        organization_ids,
    )
    await connection.execute(
        "DELETE FROM organization_memberships WHERE organization_id = ANY($1::uuid[])",
        organization_ids,
    )
    await connection.execute(
        "DELETE FROM volunteer_applications WHERE organization_id = ANY($1::uuid[])",
        organization_ids,
    )
    await connection.execute(
        """DELETE FROM organization_volunteer_access_policies
           WHERE organization_id = ANY($1::uuid[])""",
        organization_ids,
    )
    await connection.execute(
        "DELETE FROM organizations WHERE id = ANY($1::uuid[])", organization_ids
    )
    await connection.execute("DELETE FROM users WHERE id = ANY($1::uuid[])", user_ids)


def _real_approval_service(session, organization_id):
    return VolunteerAccessService(
        VolunteerAccessRepository(session, organization_id),
        AuthenticationRepository(session),
        SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_real_approval_uses_service_date_and_seven_day_policy() -> None:
    connection = await asyncpg.connect(os.environ["STRAYHUB_TEST_DATABASE_URL"])
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id = uuid4()
    user_id = uuid4()
    actor_user_id = uuid4()
    application_id = uuid4()
    service_date_id = uuid4()
    selected_service_date = date(2026, 9, 10)
    now = datetime(2026, 9, 12, 4, 0, tzinfo=timezone.utc)
    try:
        await _seed_pending_application(
            connection,
            organization_id=organization_id,
            user_id=user_id,
            actor_user_id=actor_user_id,
            application_id=application_id,
            now=now,
        )
        await connection.execute(
            """UPDATE organization_volunteer_access_policies
               SET default_grant_duration_hours = 168
               WHERE organization_id = $1""",
            organization_id,
        )
        await connection.execute(
            """INSERT INTO volunteer_application_service_dates
               (id, organization_id, application_id, service_date, status, version,
                created_at, updated_at)
               VALUES ($1, $2, $3, $4, 'pending', 1, $5, $5)""",
            service_date_id,
            organization_id,
            application_id,
            selected_service_date,
            now,
        )

        async with sessions() as session:
            _, membership, grant = await _real_approval_service(
                session, organization_id
            ).decide_application(
                application_id=application_id,
                expected_version=1,
                decision="approve",
                actor_user_id=actor_user_id,
                service_date=selected_service_date,
                now=now,
            )
            await session.commit()

        expected_start = datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc)
        expected_expiry = datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)
        assert membership is not None and grant is not None
        assert membership.valid_from == grant.valid_from == expected_start
        assert membership.expires_at == grant.expires_at == expected_expiry
        assert grant.duration_hours_used == 168
    finally:
        await _cleanup_approval_fixture(
            connection,
            organization_ids=[organization_id],
            user_ids=[user_id, actor_user_id],
        )
        await engine.dispose()
        await connection.close()


@pytest.mark.asyncio
async def test_parallel_duplicate_approval_creates_one_membership_and_one_grant() -> None:
    database_url = os.environ["STRAYHUB_TEST_DATABASE_URL"]
    connection = await asyncpg.connect(database_url)
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id = uuid4()
    user_id = uuid4()
    actor_user_id = uuid4()
    application_id = uuid4()
    now = datetime.now(timezone.utc)
    first_staged = asyncio.Event()
    allow_first_commit = asyncio.Event()
    duplicate_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    first_task: asyncio.Task[Any] | None = None
    duplicate_task: asyncio.Task[Any] | None = None

    async def first_approval():
        async with sessions() as session:
            result = await _real_approval_service(session, organization_id).decide_application(
                application_id=application_id,
                expected_version=1,
                decision="approve",
                actor_user_id=actor_user_id,
                valid_from=now,
                now=now,
            )
            first_staged.set()
            await allow_first_commit.wait()
            await session.commit()
            return result

    async def duplicate_approval():
        await first_staged.wait()
        async with sessions() as session:
            backend_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert backend_pid is not None
            duplicate_pid.set_result(backend_pid)
            with pytest.raises(DomainError, match="申請狀態已更新") as error:
                await _real_approval_service(session, organization_id).decide_application(
                    application_id=application_id,
                    expected_version=1,
                    decision="approve",
                    actor_user_id=actor_user_id,
                    valid_from=now,
                    now=now,
                )
            await session.rollback()
            return error.value

    try:
        await _seed_pending_application(
            connection,
            organization_id=organization_id,
            user_id=user_id,
            actor_user_id=actor_user_id,
            application_id=application_id,
            now=now,
        )
        first_task = asyncio.create_task(first_approval())
        duplicate_task = asyncio.create_task(duplicate_approval())
        await asyncio.wait_for(first_staged.wait(), timeout=2)
        blocked_pid = await asyncio.wait_for(duplicate_pid, timeout=2)

        async def duplicate_is_blocked() -> bool:
            while True:
                if await connection.fetchval(
                    "SELECT cardinality(pg_blocking_pids($1)) > 0", blocked_pid
                ):
                    return True
                await asyncio.sleep(0.01)

        assert await asyncio.wait_for(duplicate_is_blocked(), timeout=2)
        allow_first_commit.set()
        await asyncio.wait_for(first_task, timeout=2)
        conflict = await asyncio.wait_for(duplicate_task, timeout=2)

        assert conflict.code == "application_version_conflict"
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM organization_memberships WHERE user_id = $1",
                user_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM volunteer_access_grants WHERE application_id = $1",
                application_id,
            )
            == 1
        )
        projection = await connection.fetchrow(
            """SELECT membership.organization_id AS membership_organization_id,
                      membership.role,
                      membership.status AS membership_status,
                      membership.valid_from AS membership_valid_from,
                      membership.expires_at AS membership_expires_at,
                      access_grant.organization_id AS grant_organization_id,
                      access_grant.status AS grant_status,
                      access_grant.valid_from AS grant_valid_from,
                      access_grant.expires_at AS grant_expires_at
               FROM organization_memberships AS membership
               JOIN volunteer_access_grants AS access_grant
                 ON access_grant.membership_id = membership.id
               WHERE access_grant.application_id = $1""",
            application_id,
        )
        assert projection is not None
        assert projection["membership_organization_id"] == organization_id
        assert projection["grant_organization_id"] == organization_id
        assert projection["role"] == "VOLUNTEER"
        assert projection["membership_status"] == projection["grant_status"] == "active"
        assert projection["membership_valid_from"] == projection["grant_valid_from"] == now
        assert (
            projection["membership_expires_at"]
            == projection["grant_expires_at"]
            == now + timedelta(hours=72)
        )
    finally:
        allow_first_commit.set()
        tasks = [task for task in (first_task, duplicate_task) if task is not None]
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=2)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        await _cleanup_approval_fixture(
            connection,
            organization_ids=[organization_id],
            user_ids=[user_id, actor_user_id],
        )
        await engine.dispose()
        await connection.close()


@pytest.mark.asyncio
async def test_stale_or_cross_organization_approval_creates_no_projection() -> None:
    connection = await asyncpg.connect(os.environ["STRAYHUB_TEST_DATABASE_URL"])
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_a = uuid4()
    organization_b = uuid4()
    user_id = uuid4()
    actor_user_id = uuid4()
    application_id = uuid4()
    now = datetime.now(timezone.utc)
    try:
        await _seed_pending_application(
            connection,
            organization_id=organization_b,
            user_id=user_id,
            actor_user_id=actor_user_id,
            application_id=application_id,
            now=now,
        )
        suffix = organization_a.hex[:12]
        await connection.execute(
            """INSERT INTO organizations (id, name, code, status, created_at, updated_at)
               VALUES ($1, $2, $3, 'active', $4, $4)""",
            organization_a,
            f"Approval shelter {suffix}",
            f"approval-{suffix}",
            now,
        )
        await connection.execute(
            """INSERT INTO organization_volunteer_access_policies
               (organization_id, applications_enabled, default_grant_duration_hours, version,
                created_at, updated_at)
               VALUES ($1, true, 72, 1, $2, $2)""",
            organization_a,
            now,
        )

        async with sessions() as session:
            with pytest.raises(DomainError) as cross_org:
                await _real_approval_service(session, organization_a).decide_application(
                    application_id=application_id,
                    expected_version=1,
                    decision="approve",
                    actor_user_id=actor_user_id,
                    now=now,
                )
            assert cross_org.value.code == "application_not_found"
            assert cross_org.value.status_code == 404
            await session.rollback()

        async with sessions() as session:
            with pytest.raises(DomainError) as stale:
                await _real_approval_service(session, organization_b).decide_application(
                    application_id=application_id,
                    expected_version=0,
                    decision="approve",
                    actor_user_id=actor_user_id,
                    now=now,
                )
            assert stale.value.code == "application_version_conflict"
            assert stale.value.status_code == 409
            await session.rollback()

        assert (
            await connection.fetchval(
                "SELECT count(*) FROM organization_memberships WHERE user_id = $1",
                user_id,
            )
            == 0
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM volunteer_access_grants WHERE application_id = $1",
                application_id,
            )
            == 0
        )
    finally:
        await _cleanup_approval_fixture(
            connection,
            organization_ids=[organization_a, organization_b],
            user_ids=[user_id, actor_user_id],
        )
        await engine.dispose()
        await connection.close()
