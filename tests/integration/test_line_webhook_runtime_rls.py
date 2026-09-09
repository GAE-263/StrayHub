from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
import pytest
from scripts.configure_runtime_role import configure
from services.api.app.api import line_webhook
from services.api.app.api.errors import DomainError
from services.api.app.application.care_report_handoff_service import CareReportHandoffService
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.care_report_handoff_repository import (
    CareReportHandoffRepository,
)
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _base_database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test",
    )


async def _insert_volunteer_access(
    connection,
    *,
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
) -> None:
    application_id, grant_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    await connection.execute(
        """
        INSERT INTO organization_memberships
            (id, organization_id, user_id, role, status, valid_from, expires_at,
             access_version, medical_care_access, created_at, updated_at)
        VALUES ($1, $2, $3, 'VOLUNTEER', 'active', $4, $5, 0, false, now(), now())
        """,
        membership_id,
        organization_id,
        user_id,
        now - timedelta(hours=1),
        now + timedelta(hours=2),
    )
    await connection.execute(
        """
        INSERT INTO volunteer_applications
            (id, organization_id, user_id, status, source_channel, submitted_at,
             decided_at, version, created_at, updated_at)
        VALUES ($1, $2, $3, 'approved', 'liff', $4, $4, 1, now(), now())
        """,
        application_id,
        organization_id,
        user_id,
        now - timedelta(hours=1),
    )
    await connection.execute(
        """
        INSERT INTO volunteer_access_grants
            (id, organization_id, user_id, membership_id, application_id, status,
             valid_from, expires_at, approved_at, source_type, version,
             created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, 'active', $6, $7, $6,
                'manager_approval', 1, now(), now())
        """,
        grant_id,
        organization_id,
        user_id,
        membership_id,
        application_id,
        now - timedelta(hours=1),
        now + timedelta(hours=2),
    )


async def _seed(connection) -> SimpleNamespace:
    ids = SimpleNamespace(
        org_a=uuid4(),
        org_b=uuid4(),
        animal_a=uuid4(),
        animal_b=uuid4(),
        one=uuid4(),
        zero=uuid4(),
        multi=uuid4(),
        cross_actor=uuid4(),
        other=uuid4(),
        one_membership=uuid4(),
        multi_a_membership=uuid4(),
        multi_b_membership=uuid4(),
        cross_membership=uuid4(),
        other_membership=uuid4(),
        one_handoff=uuid4(),
        multi_handoff=uuid4(),
        other_handoff=uuid4(),
    )
    for organization_id, suffix in ((ids.org_a, "A"), (ids.org_b, "B")):
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', now(), now())
            """,
            organization_id,
            f"Runtime RLS Shelter {suffix}",
            f"RUNTIME-RLS-{suffix}-{organization_id.hex[:8]}",
        )
    for animal_id, organization_id, suffix in (
        (ids.animal_a, ids.org_a, "A"),
        (ids.animal_b, ids.org_b, "B"),
    ):
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'active', now(), now())
            """,
            animal_id,
            organization_id,
            f"Runtime Animal {suffix}",
            f"RUNTIME-{suffix}-{animal_id.hex[:8]}",
        )
    users = {
        "one": ids.one,
        "zero": ids.zero,
        "multi": ids.multi,
        "cross": ids.cross_actor,
        "other": ids.other,
    }
    ids.line_ids = {name: f"Uruntime{name}{uuid4().hex}" for name in users}
    for name, user_id in users.items():
        await connection.execute(
            """
            INSERT INTO users (id, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'active', now(), now())
            """,
            user_id,
            f"Runtime {name}",
        )
        await connection.execute(
            """
            INSERT INTO line_user_bindings
                (id, line_user_id, user_id, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', now(), now())
            """,
            uuid4(),
            ids.line_ids[name],
            user_id,
        )
    for user_id, organization_id, membership_id in (
        (ids.one, ids.org_a, ids.one_membership),
        (ids.multi, ids.org_a, ids.multi_a_membership),
        (ids.multi, ids.org_b, ids.multi_b_membership),
        (ids.cross_actor, ids.org_a, ids.cross_membership),
        (ids.other, ids.org_a, ids.other_membership),
    ):
        await _insert_volunteer_access(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
        )
    now = datetime.now(timezone.utc)
    for handoff_id, user_id, organization_id, membership_id, animal_id in (
        (ids.one_handoff, ids.one, ids.org_a, ids.one_membership, ids.animal_a),
        (ids.multi_handoff, ids.multi, ids.org_b, ids.multi_b_membership, ids.animal_b),
        (ids.other_handoff, ids.other, ids.org_a, ids.other_membership, ids.animal_a),
    ):
        await connection.execute(
            """
            INSERT INTO care_report_handoffs
                (id, organization_id, user_id, membership_id, animal_id, status,
                 expires_at, source, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, 'pending', $6, 'shelter_number', $7, $7)
            """,
            handoff_id,
            organization_id,
            user_id,
            membership_id,
            animal_id,
            now + timedelta(minutes=15),
            now,
        )
    await connection.execute(
        """
        INSERT INTO webhook_sessions
            (id, user_id, organization_id, status, expires_at, created_at, updated_at)
        VALUES ($1, $2, $3, 'active', $4, now(), now())
        """,
        uuid4(),
        ids.multi,
        ids.org_a,
        now + timedelta(hours=1),
    )
    return ids


async def _handoff_service(session, organization_id: UUID) -> CareReportHandoffService:
    animals = AnimalRepository(session, organization_id)
    return CareReportHandoffService(
        CareReportHandoffRepository(session, organization_id),
        authorization=VolunteerReportingAuthorizationService(
            AuthenticationRepository(session), animals
        ),
    )


@pytest.mark.asyncio
async def test_webhook_runtime_role_rls_matrix_and_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = urlsplit(_base_database_url())
    database = f"strayhub_line_rls_{uuid4().hex[:12]}"
    maintenance_url = urlunsplit(("postgresql", base.netloc, "/postgres", "", ""))
    owner_url = urlunsplit(("postgresql", base.netloc, f"/{database}", "", ""))
    async_url = urlunsplit(("postgresql+asyncpg", base.netloc, f"/{database}", "", ""))
    maintenance = await asyncpg.connect(maintenance_url)
    engine = None
    try:
        await maintenance.execute(f'CREATE DATABASE "{database}"')
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=dict(os.environ, DATABASE_URL=async_url),
            capture_output=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr.decode()
        await configure(async_url, apply=True)
        owner = await asyncpg.connect(owner_url)
        try:
            ids = await _seed(owner)
        finally:
            await owner.close()

        engine = create_async_engine(async_url, pool_size=1, max_overflow=0)

        @event.listens_for(engine.sync_engine, "connect")
        def use_runtime_role(connection, _record) -> None:
            connection.autocommit = True
            cursor = connection.cursor()
            cursor.execute("SET ROLE strayhub_runtime")
            cursor.close()
            connection.autocommit = False

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        # Exercise the real menu qualification query under RLS, mocking only LINE I/O.
        menu_calls = []

        async def switch_menu(line_user_id, role):
            menu_calls.append((line_user_id, role))
            return True

        with monkeypatch.context() as menu_patch:
            menu_patch.setattr(line_webhook, "_switch_rich_menu", switch_menu)
            async with sessions() as session, session.begin():
                assert await AuthenticationRepository(session).memberships(ids.one) == []
                assert await line_webhook._switch_menu_to_volunteer_if_active(
                    session, ids.line_ids["one"]
                )
                assert await AuthenticationRepository(session).memberships(ids.other) == []
                assert (
                    await AuthenticationRepository(session).get_membership(ids.one, ids.org_b)
                    is None
                )
            assert menu_calls == [(ids.line_ids["one"], "VOLUNTEER")]
            async with sessions() as session, session.begin():
                # Reused pooled connections must not retain the previous actor scope.
                assert await AuthenticationRepository(session).memberships(ids.one) == []
                assert not await line_webhook._switch_menu_to_volunteer_if_active(
                    session, ids.line_ids["zero"]
                )
                assert not await line_webhook._switch_menu_to_volunteer_if_active(
                    session, "U-unbound-runtime-menu-test"
                )
            assert len(menu_calls) == 1

        replies = []

        async def reply_next(*_args, **kwargs):
            replies.append(kwargs)

        monkeypatch.setattr(line_webhook, "_reply_next_step", reply_next)
        async with sessions() as session, session.begin():
            await line_webhook._handle_walk_report_command(
                session,
                object(),
                {"webhookEventId": "runtime-one", "replyToken": "reply-one"},
                ids.line_ids["one"],
            )
        assert len(replies) == 1

        owner = await asyncpg.connect(owner_url)
        try:
            assert (
                await owner.fetchval(
                    "SELECT status FROM care_report_handoffs WHERE id=$1", ids.one_handoff
                )
                == "consumed"
            )
            assert (
                await owner.fetchval(
                    "SELECT count(*) FROM care_report_drafts WHERE volunteer_user_id=$1", ids.one
                )
                == 1
            )
            assert (
                await owner.fetchval(
                    "SELECT count(*) FROM care_reports WHERE volunteer_user_id=$1", ids.one
                )
                == 0
            )
            assert await owner.fetchval("SELECT count(*) FROM ai_processing_jobs") == 0
            assert (
                await owner.fetchval(
                    """SELECT count(*) FROM webhook_sessions
                   WHERE user_id=$1 AND organization_id=$2 AND status='active'""",
                    ids.one,
                    ids.org_a,
                )
                == 1
            )
        finally:
            await owner.close()

        async with sessions() as session, session.begin():
            with pytest.raises(DomainError) as zero:
                await line_webhook._resolve_context(session, ids.line_ids["zero"])
            assert zero.value.code == "shelter_context_required"

        owner = await asyncpg.connect(owner_url)
        try:
            await owner.execute("DELETE FROM webhook_sessions WHERE user_id=$1", ids.multi)
        finally:
            await owner.close()
        async with sessions() as session, session.begin():
            with pytest.raises(DomainError) as multiple:
                await line_webhook._resolve_context(session, ids.line_ids["multi"])
            assert multiple.value.code == "shelter_context_required"

        owner = await asyncpg.connect(owner_url)
        try:
            await owner.execute(
                """INSERT INTO webhook_sessions
                   (id,user_id,organization_id,status,expires_at,created_at,updated_at)
                   VALUES ($1,$2,$3,'active',now()+interval '1 hour',now(),now())""",
                uuid4(),
                ids.multi,
                ids.org_a,
            )
        finally:
            await owner.close()
        async with sessions() as session, session.begin():
            user_id, organization_id, _, _ = await line_webhook._resolve_context(
                session, ids.line_ids["multi"]
            )
            assert user_id == ids.multi
            assert organization_id == ids.org_a
            service = await _handoff_service(session, ids.org_a)
            with pytest.raises(DomainError) as cross_org:
                await service.consume_pending_handoff(
                    user_id=ids.multi,
                    organization_id=ids.org_a,
                )
            assert cross_org.value.code == "no_pending_handoff"

        async with sessions() as session, session.begin():
            user_id, organization_id, _, _ = await line_webhook._resolve_context(
                session, ids.line_ids["cross"]
            )
            service = await _handoff_service(session, organization_id)
            with pytest.raises(DomainError) as cross_user:
                await service.consume_pending_handoff(
                    user_id=user_id,
                    organization_id=organization_id,
                )
            assert cross_user.value.code == "no_pending_handoff"

        async with sessions() as session, session.begin():
            assert (
                await session.scalar(
                    text("SELECT NULLIF(current_setting('app.auth_user_id', true), '')")
                )
                is None
            )
            assert (
                await session.scalar(
                    text("SELECT NULLIF(current_setting('app.current_org_id', true), '')")
                )
                is None
            )
            assert await session.scalar(text("SELECT count(*) FROM webhook_sessions")) == 0
            assert await session.scalar(text("SELECT count(*) FROM organization_memberships")) == 0

        owner = await asyncpg.connect(owner_url)
        try:
            assert (
                await owner.fetchval(
                    "SELECT status FROM care_report_handoffs WHERE id=$1", ids.multi_handoff
                )
                == "pending"
            )
            assert (
                await owner.fetchval(
                    "SELECT status FROM care_report_handoffs WHERE id=$1", ids.other_handoff
                )
                == "pending"
            )
        finally:
            await owner.close()
    finally:
        if engine is not None:
            await engine.dispose()
        await maintenance.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        await maintenance.close()
