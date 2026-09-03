"""Real HTTP dependencies and transactions on a disposable runtime-role database."""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from scripts.configure_runtime_role import configure
from services.api.app.api.dependencies import request_session
from services.api.app.application.audit_service import AuditService
from services.api.app.application.care_report_handoff_service import CareReportHandoffService
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.main import app
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.care_report_handoff import CareReportHandoff
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    Organization,
    OrganizationMembership,
    SessionRecord,
    User,
    WebhookSession,
)
from services.api.app.persistence.models.volunteer_access import (
    VolunteerAccessGrant,
    VolunteerApplication,
)
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.care_report_handoff_repository import (
    CareReportHandoffRepository,
)
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def runtime_api(request):
    base = urlsplit(os.environ["STRAYHUB_TEST_DATABASE_URL"])
    database = f"strayhub_switch_{uuid4().hex[:12]}"
    maintenance_url = urlunsplit(("postgresql", base.netloc, "/postgres", "", ""))
    url = urlunsplit(("postgresql+asyncpg", base.netloc, f"/{database}", "", ""))
    maintenance = await asyncpg.connect(maintenance_url)
    await maintenance.execute(f'CREATE DATABASE "{database}"')
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    orgs = [uuid4() for _ in range(3)]
    user_id, session_id = uuid4(), uuid4()
    line_user_id = f"U{uuid4().hex}"
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=dict(os.environ, DATABASE_URL=url),
            capture_output=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stderr.decode()
        before = await configure(url)
        assert len(before["missing_grants"]) == 9
        await configure(url, apply=True)
        assert (await configure(url))["missing_grants"] == []
        async with factory() as session, session.begin():
            session.add(User(id=user_id, display_name="Switch test", status="active"))
            await session.flush()
            session.add(
                LineUserBinding(
                    line_user_id=line_user_id,
                    user_id=user_id,
                    status="active",
                )
            )
            session.add_all(
                Organization(id=org, code=f"S-{org}", name=f"Shelter {i}", status="active")
                for i, org in enumerate(orgs)
            )
            await session.flush()
            now = datetime.now(timezone.utc)
            all_shelters = getattr(request, "param", "STAFF") == "ALL_SHELTERS"
            for org in orgs if all_shelters else orgs[:2]:
                membership = OrganizationMembership(
                    organization_id=org,
                    user_id=user_id,
                    role="STAFF" if all_shelters else getattr(request, "param", "STAFF"),
                    status="active",
                    valid_from=now - timedelta(hours=1),
                    expires_at=now + timedelta(hours=1),
                )
                session.add(membership)
                await session.flush()
                if membership.role == "VOLUNTEER":
                    application = VolunteerApplication(
                        organization_id=org,
                        user_id=user_id,
                        status="approved",
                        source_channel="management",
                        submitted_at=now,
                        decided_at=now,
                        decided_by_user_id=user_id,
                    )
                    session.add(application)
                    await session.flush()
                    session.add(
                        VolunteerAccessGrant(
                            organization_id=org,
                            user_id=user_id,
                            membership_id=membership.id,
                            application_id=application.id,
                            status="active",
                            valid_from=membership.valid_from,
                            expires_at=membership.expires_at,
                            approved_at=now,
                            approved_by_user_id=user_id,
                            policy_version_used=1,
                            duration_hours_used=2,
                        )
                    )
            session.add_all(
                Animal(organization_id=org, name=f"Animal {i}", status="active")
                for i, org in enumerate(orgs)
            )
            session.add(
                SessionRecord(
                    id=session_id,
                    user_id=user_id,
                    active_organization_id=orgs[0],
                    status="active",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            session.add(
                WebhookSession(
                    user_id=user_id,
                    organization_id=orgs[0],
                    status="active",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
        await engine.dispose()

        @event.listens_for(engine.sync_engine, "connect")
        def runtime_role(connection, _record):
            connection.autocommit = True
            cursor = connection.cursor()
            cursor.execute("SET ROLE strayhub_runtime")
            cursor.close()
            connection.autocommit = False

        pids = set()

        async def sessions():
            async with factory() as session:
                assert await session.scalar(text("SELECT current_user")) == "strayhub_runtime"
                assert not await session.scalar(
                    text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")
                )
                assert not await session.scalar(
                    text("SELECT nullif(current_setting('app.current_org_id',true),'')")
                )
                assert (
                    await session.scalar(
                        text("SELECT coalesce(current_setting('app.platform_scope',true),'')")
                    )
                    != "true"
                )
                pids.add(await session.scalar(text("SELECT pg_backend_pid()")))
                yield session

        app.dependency_overrides[request_session] = sessions
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Session-Id": str(session_id)},
        ) as client:
            yield client, factory, orgs, user_id, session_id, pids
        assert len(pids) == 1, "Requests must reuse the exact runtime connection"
    finally:
        app.dependency_overrides.pop(request_session, None)
        await engine.dispose()
        await maintenance.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        await maintenance.close()


async def test_authorized_switch_audit_scope_and_pool_reuse(runtime_api):
    client, factory, orgs, user, sid, _ = runtime_api
    available = await client.get("/v1/organizations")
    assert available.status_code == 200, available.text
    assert {row["id"] for row in available.json()["items"]} == {str(org) for org in orgs[:2]}
    for org in (orgs[1], orgs[0], orgs[1]):
        response = await client.put(
            "/v1/auth/active-shelter-context", json={"organization_id": str(org)}
        )
        assert response.status_code == 200, response.text
        assert response.json()["organization_id"] == str(org)
        current = await client.get("/v1/auth/active-shelter-context")
        assert current.json()["organization_id"] == str(org)
        async with factory() as session:
            await set_organization_scope(session, org)
            webhook_sessions = (
                await session.scalars(
                    select(WebhookSession).where(
                        WebhookSession.user_id == user,
                        WebhookSession.status == "active",
                    )
                )
            ).all()
            assert len(webhook_sessions) == 1
            assert webhook_sessions[0].organization_id == org
        animals = await client.get("/v1/management/animals")
        assert animals.status_code == 200, animals.text
        assert {row["organization_id"] for row in animals.json()["items"]} == {str(org)}
    async with factory() as session:
        await set_organization_scope(session, orgs[1])
        records = (await session.scalars(select(AuditRecord))).all()
        assert len(records) == 2
        for record in records:
            assert record.organization_id == orgs[1]
            assert record.actor_user_id == user
            assert record.action == "shelter_context.switched"
            assert record.resource_type == "SessionRecord" and record.resource_id == sid
            assert record.before_data == {"organization_id": str(orgs[0])}
            assert record.after_data == {"organization_id": str(orgs[1])}


@pytest.mark.parametrize("runtime_api", ["VOLUNTEER"], indirect=True)
async def test_initial_selection_audit_uses_target_scope(runtime_api):
    client, factory, orgs, user, sid, _ = runtime_api
    async with factory() as session, session.begin():
        record = await session.get(SessionRecord, sid)
        record.active_organization_id = None
    response = await client.put(
        "/v1/auth/active-shelter-context", json={"organization_id": str(orgs[1])}
    )
    assert response.status_code == 200, response.text
    assert response.json()["organization_id"] == str(orgs[1])
    assert (await client.get("/v1/auth/active-shelter-context")).json()["organization_id"] == str(
        orgs[1]
    )

    async with factory() as session, session.begin():
        await set_organization_scope(session, orgs[1])
        binding = await AuthenticationRepository(session).get_line_binding_for_user(user)
        assert binding is not None and binding.user_id == user
        webhook_sessions = (
            await session.scalars(
                select(WebhookSession).where(
                    WebhookSession.user_id == user,
                    WebhookSession.status == "active",
                )
            )
        ).all()
        assert len(webhook_sessions) == 1
        assert webhook_sessions[0].organization_id == orgs[1]

        membership = await AuthenticationRepository(session).get_effective_membership(user, orgs[1])
        animal = (await AnimalRepository(session, orgs[1]).list_active())[0]
        assert membership is not None
        now = datetime.now(timezone.utc)
        handoff = CareReportHandoff(
            organization_id=orgs[1],
            user_id=user,
            membership_id=membership.id,
            animal_id=animal.id,
            status="pending",
            source="liff_scan",
            expires_at=now + timedelta(minutes=15),
        )
        session.add(handoff)
        await session.flush()
        consumed = await CareReportHandoffService(
            CareReportHandoffRepository(session, orgs[1]),
            authorization=VolunteerReportingAuthorizationService(
                AuthenticationRepository(session), AnimalRepository(session, orgs[1])
            ),
        ).consume_pending_handoff(user_id=user, organization_id=orgs[1])
        assert consumed.id == handoff.id
        assert consumed.status == "consumed"

    async with factory() as session:
        await set_organization_scope(session, orgs[0])
        assert (
            await session.scalars(select(WebhookSession).where(WebhookSession.status == "active"))
        ).all() == []


async def test_same_shelter_selection_preserves_webhook_session(runtime_api):
    client, factory, orgs, user, _, _ = runtime_api
    async with factory() as session:
        await set_organization_scope(session, orgs[0])
        original = await session.scalar(
            select(WebhookSession).where(
                WebhookSession.user_id == user,
                WebhookSession.status == "active",
            )
        )
        assert original is not None
        original_id = original.id

    response = await client.put(
        "/v1/auth/active-shelter-context", json={"organization_id": str(orgs[0])}
    )
    assert response.status_code == 200, response.text

    async with factory() as session:
        await set_organization_scope(session, orgs[0])
        active = (
            await session.scalars(
                select(WebhookSession).where(
                    WebhookSession.user_id == user,
                    WebhookSession.status == "active",
                )
            )
        ).all()
        assert [item.id for item in active] == [original_id]


async def test_revoked_binding_during_switch_does_not_change_context(runtime_api, monkeypatch):
    client, factory, orgs, user, _, _ = runtime_api

    async def revoked_while_waiting(self, line_user_id):
        return None

    monkeypatch.setattr(AuthenticationRepository, "lock_line_binding", revoked_while_waiting)
    response = await client.put(
        "/v1/auth/active-shelter-context", json={"organization_id": str(orgs[1])}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "line_binding_invalid"
    assert (await client.get("/v1/auth/active-shelter-context")).json()["organization_id"] == str(
        orgs[0]
    )

    async with factory() as session:
        await set_organization_scope(session, orgs[0])
        active_a = (
            await session.scalars(
                select(WebhookSession).where(
                    WebhookSession.user_id == user,
                    WebhookSession.status == "active",
                )
            )
        ).all()
        assert len(active_a) == 1
    async with factory() as session:
        await set_organization_scope(session, orgs[1])
        active_b = (
            await session.scalars(
                select(WebhookSession).where(
                    WebhookSession.user_id == user,
                    WebhookSession.status == "active",
                )
            )
        ).all()
        assert active_b == []


@pytest.mark.parametrize("failure", ["audit", "commit"])
async def test_failed_write_preserves_a_and_has_no_success_audit(runtime_api, monkeypatch, failure):
    client, factory, orgs, _, sid, _ = runtime_api
    original = AuditService.record

    async def failed_audit(self, **kwargs):
        assert await self.session.scalar(
            text("SELECT current_setting('app.current_org_id',true)")
        ) == str(orgs[1])
        await original(self, **kwargs)  # Flush both session B and its audit first.
        if failure == "audit":
            await self.session.execute(text("SELECT 1/0"))
        else:
            # Deferrable FK fails only at the endpoint's real COMMIT.
            await self.session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            record = await self.session.get(SessionRecord, sid)
            record.user_id = uuid4()

    if failure == "commit":
        # Setup-only DDL on this disposable DB, not an application privilege.
        base = urlsplit(os.environ["STRAYHUB_TEST_DATABASE_URL"])
        url = urlunsplit(("postgresql", base.netloc, "/" + factory.kw["bind"].url.database, "", ""))
        owner = await asyncpg.connect(url)
        await owner.execute(
            "ALTER TABLE session_records ALTER CONSTRAINT "
            "session_records_user_id_fkey DEFERRABLE INITIALLY DEFERRED"
        )
        await owner.close()
    monkeypatch.setattr(AuditService, "record", failed_audit)
    response = await client.put(
        "/v1/auth/active-shelter-context", json={"organization_id": str(orgs[1])}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
    assert not any(value in response.text for value in ("42501", "postgres", "audit_records"))
    current = await client.get("/v1/auth/active-shelter-context")
    assert current.json()["organization_id"] == str(orgs[0])
    async with factory() as session:
        await set_organization_scope(session, orgs[1])
        assert (await session.scalars(select(AuditRecord))).all() == []
        assert (
            await session.scalars(select(WebhookSession).where(WebhookSession.status == "active"))
        ).all() == []
    async with factory() as session:
        await set_organization_scope(session, orgs[0])
        assert (
            len(
                (
                    await session.scalars(
                        select(WebhookSession).where(WebhookSession.status == "active")
                    )
                ).all()
            )
            == 1
        )


async def test_unauthorized_target_preserves_a(runtime_api):
    client, factory, orgs, _, _, _ = runtime_api
    available = await client.get("/v1/organizations")
    assert available.status_code == 200
    assert len(available.json()["items"]) == 2
    response = await client.put(
        "/v1/auth/active-shelter-context", json={"organization_id": str(orgs[2])}
    )
    assert response.status_code == 404
    assert "Shelter 2" not in response.text
    current = await client.get("/v1/auth/active-shelter-context")
    assert current.json()["organization_id"] == str(orgs[0])
    async with factory() as session:
        await set_organization_scope(session, orgs[2])
        assert (await session.scalars(select(AuditRecord))).all() == []


@pytest.mark.parametrize("runtime_api", ["VOLUNTEER"], indirect=True)
async def test_volunteer_current_and_target_grants_checked_in_exact_scope(runtime_api):
    client, factory, orgs, _, _, _ = runtime_api
    response = await client.put(
        "/v1/auth/active-shelter-context", json={"organization_id": str(orgs[1])}
    )
    assert response.status_code == 200, response.text
    assert (await client.get("/v1/animals")).status_code == 200
    async with factory() as session, session.begin():
        await set_organization_scope(session, orgs[0])
        grant = await session.scalar(select(VolunteerAccessGrant))
        grant.status = "revoked"
        grant.revoked_at = datetime.now(timezone.utc)
        grant.revoked_by_user_id = runtime_api[3]
        grant.revocation_reason = "Context switch regression"
    response = await client.put(
        "/v1/auth/active-shelter-context", json={"organization_id": str(orgs[0])}
    )
    assert response.status_code == 404
    assert (await client.get("/v1/auth/active-shelter-context")).json()["organization_id"] == str(
        orgs[1]
    )
    available = await client.get("/v1/organizations")
    assert [row["id"] for row in available.json()["items"]] == [str(orgs[1])]
    async with factory() as session:
        user_id = (await session.get(SessionRecord, runtime_api[4])).user_id
        access = await AuthenticationRepository(session).effective_organization_access(user_id)
        assert [org.id for _, org in access] == [orgs[1]]


@pytest.mark.parametrize("runtime_api", ["ALL_SHELTERS"], indirect=True)
async def test_three_shelter_http_switching_never_returns_stale_animal_rows(runtime_api):
    client, _, orgs, _, _, _ = runtime_api
    available = await client.get("/v1/organizations")
    assert len(available.json()["items"]) == 3
    for org in (*orgs, orgs[0]):
        switched = await client.put(
            "/v1/auth/active-shelter-context", json={"organization_id": str(org)}
        )
        assert switched.status_code == 200
        animals = await client.get("/v1/management/animals")
        assert animals.status_code == 200
        assert len(animals.json()["items"]) == 1
        assert animals.json()["items"][0]["organization_id"] == str(org)
