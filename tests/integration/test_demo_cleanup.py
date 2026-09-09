"""Real PostgreSQL cleanup graph, retention, and explicit test-fixture regression."""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest
from scripts import cleanup_legacy_demo_fixtures as cleanup_module
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import (
    Organization,
    OrganizationMembership,
    SessionRecord,
    User,
)
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def cleanup_db(monkeypatch):
    base = urlsplit(
        os.getenv(
            "STRAYHUB_TEST_DATABASE_URL", "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub"
        )
    )
    database = "strayhub_cleanup_test_" + uuid4().hex[:10]
    maintenance = await asyncpg.connect(
        urlunsplit(("postgresql", base.netloc, "/postgres", "", ""))
    )
    await maintenance.execute(f'CREATE DATABASE "{database}"')
    url = urlunsplit(("postgresql+asyncpg", base.netloc, "/" + database, "", ""))
    engine = create_async_engine(url)
    try:
        env = dict(
            os.environ,
            DATABASE_URL=url,
            DATABASE_MIGRATION_URL=url,
            STRAYHUB_TEST_DATABASE_URL=url.replace("postgresql+asyncpg://", "postgresql://", 1),
            STRAYHUB_ALLOW_EPHEMERAL_TEST_DATABASE="1",
            APP_ENV="test",
        )
        for module, args in [("alembic", ["upgrade", "head"]), ("scripts.seed_test_fixtures", [])]:
            r = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", module, *args],
                env=env,
                capture_output=True,
                timeout=120,
            )
            assert r.returncode == 0, r.stderr.decode()
        monkeypatch.setattr(cleanup_module, "engine", engine)
        yield engine
    finally:
        await engine.dispose()
        await maintenance.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        await maintenance.close()


async def test_fk_cleanup_preview_retains_unknown_data_vocabulary_and_is_idempotent(cleanup_db):
    oid, uid, animal = uuid4(), uuid4(), uuid4()
    async with cleanup_db.begin() as c:
        await c.execute(
            insert(Organization).values(
                id=oid, code="DO-NOT-DELETE", name="Retained", status="active"
            )
        )
        await c.execute(
            insert(User).values(
                id=uid, username="local-real-person", display_name="Retained user", status="active"
            )
        )
        await c.execute(
            insert(Animal).values(
                id=animal, organization_id=oid, name="Retained animal", status="active"
            )
        )
        # Known test user now has retained tenant access: preserve it, not its fixture membership.
        staff = await c.scalar(text("SELECT id FROM users WHERE username='local-staff-a'"))
        await c.execute(
            insert(OrganizationMembership).values(
                organization_id=oid, user_id=staff, role="STAFF", status="active"
            )
        )
        vocab = await c.scalar(
            text("SELECT count(*) FROM observation_options WHERE organization_id IS NULL")
        )
        retained = (
            await c.execute(text("SELECT to_jsonb(a) FROM animals a WHERE id=:id"), {"id": animal})
        ).scalar_one()
    before = await cleanup_module.cleanup()
    assert not before["applied"] and before["delete_counts"]["organizations"] == 3
    async with cleanup_db.connect() as c:
        assert await c.scalar(text("SELECT count(*) FROM organizations WHERE code='ORG-A'")) == 1
    result = await cleanup_module.cleanup(apply=True)
    assert result["retained_referenced_fixture_users"] == 1
    async with cleanup_db.connect() as c:
        assert (await c.scalars(text("SELECT code FROM organizations"))).all() == ["DO-NOT-DELETE"]
        assert (
            await c.scalar(
                text("SELECT count(*) FROM observation_options WHERE organization_id IS NULL")
            )
            == vocab
            > 0
        )
        assert (
            await c.execute(text("SELECT to_jsonb(a) FROM animals a WHERE id=:id"), {"id": animal})
        ).scalar_one() == retained
        assert (
            await c.scalar(
                text(
                    "SELECT count(*) FROM users "
                    "WHERE username IN ('local-staff-a','local-real-person')"
                )
            )
            == 2
        )
        assert await c.scalar(text("SELECT count(*) FROM volunteer_applications")) == 0
    assert (await cleanup_module.cleanup(apply=True))["delete_counts"] == {}


async def test_cross_tenant_dependency_aborts_before_deletion(cleanup_db):
    async with cleanup_db.begin() as c:
        area = await c.scalar(text("SELECT id FROM shelter_areas LIMIT 1"))
        oid = uuid4()
        await c.execute(
            insert(Organization).values(id=oid, code="KEEP", name="Keep", status="active")
        )
        await c.execute(
            insert(Animal).values(
                organization_id=oid, area_id=area, name="Cross reference", status="active"
            )
        )
    with pytest.raises(RuntimeError, match="cross_tenant_reference:animals"):
        await cleanup_module.cleanup(apply=True)
    async with cleanup_db.connect() as c:
        assert await c.scalar(text("SELECT count(*) FROM organizations")) == 4


async def test_demo_accounts_are_idempotent_and_volunteers_are_single_tenant(
    cleanup_db, monkeypatch
):
    from scripts import seed_demo_accounts
    from scripts.local_demo import DEMO_SHELTERS
    from scripts.seed_furkids_demo import _seed_identity
    from sqlalchemy import select

    factory = async_sessionmaker(cleanup_db, expire_on_commit=False)
    monkeypatch.setattr(seed_demo_accounts, "session_factory", factory)
    monkeypatch.setattr(seed_demo_accounts, "guard", lambda: None)
    async with factory() as session, session.begin():
        for code, name in DEMO_SHELTERS.items():
            org = Organization(code=code, name=name, status="active")
            session.add(org)
            await session.flush()
            if code == "FURKIDS-ASIA":
                await _seed_identity(session, org, "integration-synthetic-password")
    await seed_demo_accounts.seed(password="integration-synthetic-password")
    async with factory() as session:
        before = set(
            (await session.scalars(select(User.id).where(User.username.like("demo-%")))).all()
        )
    async with factory() as session, session.begin():
        furkids_volunteer_id = await session.scalar(
            select(User.id).where(User.username == "demo-furkids-volunteer")
        )
        assert furkids_volunteer_id is not None
        session.add(
            SessionRecord(
                user_id=furkids_volunteer_id,
                status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
    await seed_demo_accounts.seed(password="integration-synthetic-password")
    async with factory() as session:
        after = set(
            (await session.scalars(select(User.id).where(User.username.like("demo-%")))).all()
        )
        assert before == after and len(after) == 5
        assert (
            await session.scalar(
                select(SessionRecord.status).where(SessionRecord.user_id.in_(after))
            )
            == "expired"
        )
        counts = dict(
            (
                await session.execute(
                    text("""SELECT u.username,count(m.id)
            FROM users u JOIN organization_memberships m ON m.user_id=u.id
            WHERE u.username LIKE 'demo-%' GROUP BY u.username""")
                )
            ).all()
        )
        assert counts == {
            "demo-furkids-admin": 3,
            "demo-furkids-volunteer": 1,
            "demo-xindian-volunteer": 1,
            "demo-wugu-volunteer": 1,
        }
        assert (
            await session.scalar(
                text("""SELECT count(*) FROM volunteer_access_grants g
            JOIN users u ON u.id=g.user_id WHERE u.username LIKE 'demo-%'
            AND g.status='active' AND g.valid_from<=now() AND g.expires_at>now()""")
            )
            == 3
        )
        assert (
            await session.scalar(
                text("""SELECT count(*) FROM organization_volunteer_access_policies p
            JOIN organizations o ON o.id=p.organization_id WHERE o.code IN
            ('FURKIDS-ASIA','MOA-SHELTER-51','MOA-SHELTER-58')
            AND p.default_grant_duration_hours=168""")
            )
            == 3
        )
        assert (
            await session.scalar(
                text("""SELECT count(*) FROM daily_reportable_scopes s
            JOIN organizations o ON o.id=s.organization_id WHERE o.code IN
            ('FURKIDS-ASIA','MOA-SHELTER-51','MOA-SHELTER-58')""")
            )
            == 0
        )
        assert (
            await session.scalar(
                text("""SELECT count(*) FROM organization_volunteer_access_policies p
            JOIN organizations o ON o.id=p.organization_id WHERE o.code IN
            ('FURKIDS-ASIA','MOA-SHELTER-51','MOA-SHELTER-58')
            AND p.applications_enabled""")
            )
            == 3
        )
