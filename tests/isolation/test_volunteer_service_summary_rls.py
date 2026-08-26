from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MethodType
from uuid import UUID, uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.volunteer_service_summary import (
    SUMMARY_PURPOSE,
    VolunteerServiceSummaryService,
)
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.persistence.database.scope import (
    set_organization_scope,
    set_platform_scope,
    set_platform_support_scope,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from services.api.app.persistence.repositories.volunteer_service_summary_repository import (
    VolunteerServiceSummaryRepository,
)
from sqlalchemy import Select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _database_url() -> str:
    value = os.environ.get("STRAYHUB_TEST_DATABASE_URL")
    if not value:
        raise RuntimeError("STRAYHUB_TEST_DATABASE_URL is required for PostgreSQL isolation tests")
    return value


@dataclass(frozen=True)
class SummaryFixture:
    organization_a: UUID
    organization_b: UUID
    organization_c: UUID
    reviewer_a: UUID
    inactive_reviewer: UUID
    volunteer_x: UUID
    volunteer_y: UUID
    application_x: UUID
    report_a: UUID
    report_b: UUID
    report_c: UUID


async def _create_fixture(connection: asyncpg.Connection) -> SummaryFixture:
    organization_a, organization_b, organization_c = (uuid4(), uuid4(), uuid4())
    reviewer_a, inactive_reviewer, volunteer_x, volunteer_y = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    application_x = uuid4()
    report_a, report_b, report_c = uuid4(), uuid4(), uuid4()
    membership_reviewer = uuid4()
    membership_inactive = uuid4()
    membership_x_a, membership_x_b, membership_y_c = uuid4(), uuid4(), uuid4()
    animal_a, animal_b, animal_c = uuid4(), uuid4(), uuid4()
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    expires_at = now + timedelta(days=365)

    await connection.executemany(
        """
        INSERT INTO organizations (id, name, code, status, created_at, updated_at)
        VALUES ($1, $2, $3, 'active', $4, $4)
        """,
        [
            (organization_a, "Shelter A", f"RLS-A-{organization_a.hex[:10]}", now),
            (organization_b, "Shelter B", f"RLS-B-{organization_b.hex[:10]}", now),
            (organization_c, "Shelter C", f"RLS-C-{organization_c.hex[:10]}", now),
        ],
    )
    await connection.executemany(
        """
        INSERT INTO users (id, username, display_name, status, created_at, updated_at)
        VALUES ($1, $2, $3, 'active', $4, $4)
        """,
        [
            (reviewer_a, f"reviewer-{reviewer_a.hex[:10]}", "Reviewer A", now),
            (
                inactive_reviewer,
                f"inactive-{inactive_reviewer.hex[:10]}",
                "Inactive reviewer",
                now,
            ),
            (volunteer_x, f"volunteer-x-{volunteer_x.hex[:10]}", "Volunteer X", now),
            (volunteer_y, f"volunteer-y-{volunteer_y.hex[:10]}", "Volunteer Y", now),
        ],
    )
    await connection.executemany(
        """
        INSERT INTO organization_memberships
            (id, organization_id, user_id, role, status, valid_from, expires_at,
             access_version, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, 0, $6, $6)
        """,
        [
            (membership_reviewer, organization_a, reviewer_a, "SHELTER_ADMIN", "active", now, None),
            (
                membership_inactive,
                organization_a,
                inactive_reviewer,
                "SHELTER_ADMIN",
                "suspended",
                now,
                None,
            ),
            (membership_x_a, organization_a, volunteer_x, "VOLUNTEER", "active", now, expires_at),
            (membership_x_b, organization_b, volunteer_x, "VOLUNTEER", "active", now, expires_at),
            (membership_y_c, organization_c, volunteer_y, "VOLUNTEER", "active", now, expires_at),
        ],
    )
    await connection.executemany(
        """
        INSERT INTO animals (id, organization_id, name, status, created_at, updated_at)
        VALUES ($1, $2, $3, 'active', $4, $4)
        """,
        [
            (animal_a, organization_a, "Synthetic animal A", now),
            (animal_b, organization_b, "Synthetic animal B", now),
            (animal_c, organization_c, "Synthetic animal C", now),
        ],
    )
    await connection.execute(
        """
        INSERT INTO volunteer_applications
            (id, organization_id, user_id, status, source_channel, submitted_at,
             created_at, updated_at, version)
        VALUES ($1, $2, $3, 'pending', 'test', $4, $4, $4, 1)
        """,
        application_x,
        organization_a,
        volunteer_x,
        now,
    )
    await connection.executemany(
        """
        INSERT INTO care_reports
            (id, organization_id, animal_id, volunteer_user_id, membership_id,
             answers, answer_snapshots, animal_name_snapshot, shelter_number_snapshot,
             note, status, ai_job_status, submitted_at, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10,
                $11, 'completed', $12, $12, $12)
        """,
        [
            (
                report_a,
                organization_a,
                animal_a,
                volunteer_x,
                membership_x_a,
                '{"private":"synthetic-answer-a"}',
                '{"private":"synthetic-snapshot-a"}',
                "Synthetic animal A",
                "RLS-A-ANIMAL",
                "synthetic-care-note-a",
                "saved",
                now,
            ),
            (
                report_b,
                organization_b,
                animal_b,
                volunteer_x,
                membership_x_b,
                '{"private":"synthetic-answer-b"}',
                '{"private":"synthetic-snapshot-b"}',
                "Synthetic animal B",
                "RLS-B-ANIMAL",
                "synthetic-care-note-b",
                "archived",
                now - timedelta(days=1),
            ),
            (
                report_c,
                organization_c,
                animal_c,
                volunteer_y,
                membership_y_c,
                '{"private":"synthetic-answer-c"}',
                '{"private":"synthetic-snapshot-c"}',
                "Synthetic animal C",
                "RLS-C-ANIMAL",
                "synthetic-care-note-c",
                "saved",
                now,
            ),
        ],
    )
    return SummaryFixture(
        organization_a,
        organization_b,
        organization_c,
        reviewer_a,
        inactive_reviewer,
        volunteer_x,
        volunteer_y,
        application_x,
        report_a,
        report_b,
        report_c,
    )


async def _delete_fixture(connection: asyncpg.Connection, fixture: SummaryFixture) -> None:
    await connection.execute(
        "DELETE FROM audit_records WHERE resource_id = $1", fixture.application_x
    )
    await connection.execute(
        "DELETE FROM care_reports WHERE id = ANY($1::uuid[])",
        [fixture.report_a, fixture.report_b, fixture.report_c],
    )
    await connection.execute(
        "DELETE FROM volunteer_applications WHERE id = $1", fixture.application_x
    )
    await connection.execute(
        "DELETE FROM animals WHERE organization_id = ANY($1::uuid[])",
        [fixture.organization_a, fixture.organization_b, fixture.organization_c],
    )
    await connection.execute(
        "DELETE FROM organization_memberships WHERE organization_id = ANY($1::uuid[])",
        [fixture.organization_a, fixture.organization_b, fixture.organization_c],
    )
    await connection.execute(
        "DELETE FROM users WHERE id = ANY($1::uuid[])",
        [fixture.reviewer_a, fixture.inactive_reviewer, fixture.volunteer_x, fixture.volunteer_y],
    )
    await connection.execute(
        "DELETE FROM organizations WHERE id = ANY($1::uuid[])",
        [fixture.organization_a, fixture.organization_b, fixture.organization_c],
    )


def _runtime_engine(database_url: str):
    return create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))


@pytest.mark.asyncio
async def test_real_postgres_cross_shelter_summary_and_restoration() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    engine = _runtime_engine(database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fixture = await _create_fixture(owner)
    try:
        async with maker() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
                await set_organization_scope(session, fixture.organization_a)
                access_repository = VolunteerAccessRepository(session, fixture.organization_a)
                assert await access_repository.application_detail(fixture.application_x) is not None
                assert await access_repository.application(fixture.application_x) is not None

                other_application = await session.execute(
                    text(
                        "SELECT id FROM volunteer_applications "
                        "WHERE organization_id = :organization_id"
                    ),
                    {"organization_id": fixture.organization_b},
                )
                assert other_application.first() is None

                summary_repository = VolunteerServiceSummaryRepository(
                    session, fixture.organization_a
                )
                page = await VolunteerServiceSummaryService(
                    access_repository,
                    summary_repository,
                    audit=AuditService(session),
                ).for_application(
                    fixture.application_x,
                    tenant_context=TenantContext(
                        fixture.reviewer_a, fixture.organization_a, "SHELTER_ADMIN"
                    ),
                    purpose_code=SUMMARY_PURPOSE,
                    cursor=None,
                    cursor_secret="real-rls-test-secret",
                    limit=100,
                )
                assert {item.organization_id for item in page.items} == {
                    fixture.organization_a,
                    fixture.organization_b,
                }
                assert fixture.organization_c not in {item.organization_id for item in page.items}
                assert all(
                    set(item.__dict__)
                    == {
                        "organization_id",
                        "organization_name",
                        "service_date",
                        "service_status",
                        "record_count",
                        "source",
                    }
                    for item in page.items
                )
                assert "synthetic-answer" not in repr(page.items)
                assert "synthetic-care-note" not in repr(page.items)

                assert await access_repository.application(fixture.application_x) is not None
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM organizations WHERE id = :organization_id"),
                        {"organization_id": fixture.organization_b},
                    )
                    == 0
                )

            async with session.begin():
                await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
                await set_organization_scope(session, fixture.organization_a)
                await set_platform_scope(session)
                await set_organization_scope(session, fixture.organization_a)
                assert (
                    await session.scalar(text("SELECT current_setting('app.platform_scope', true)"))
                    == "false"
                )
                assert await session.scalar(
                    text("SELECT current_setting('app.current_org_id', true)")
                ) == str(fixture.organization_a)
                access_repository = VolunteerAccessRepository(session, fixture.organization_a)
                assert await access_repository.application(fixture.application_x) is not None
                assert await access_repository.application(UUID(int=0)) is None
    finally:
        await _delete_fixture(owner, fixture)
        await owner.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_postgres_summary_restores_scope_after_exception() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    engine = _runtime_engine(database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fixture = await _create_fixture(owner)
    try:
        async with maker() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
                await set_organization_scope(session, fixture.organization_a)
                repository = VolunteerServiceSummaryRepository(session, fixture.organization_a)
                original_execute = session.execute

                async def fail_select(self, statement, *args, **kwargs):
                    # A PostgreSQL error would abort the transaction; this Python
                    # exception exercises the repository finally path while keeping
                    # the transaction valid for the visibility assertion below.
                    if isinstance(statement, Select):
                        raise RuntimeError("forced summary query failure")
                    return await original_execute(statement, *args, **kwargs)

                session.execute = MethodType(fail_select, session)  # type: ignore[method-assign]
                with pytest.raises(RuntimeError, match="forced summary query failure"):
                    await repository.list_for_subject(fixture.volunteer_x)
                session.execute = original_execute  # type: ignore[method-assign]

                assert (
                    await session.scalar(text("SELECT current_setting('app.platform_scope', true)"))
                    == "false"
                )
                access_repository = VolunteerAccessRepository(session, fixture.organization_a)
                assert await access_repository.application(fixture.application_x) is not None
                assert await access_repository.application(UUID(int=0)) is None
    finally:
        await _delete_fixture(owner, fixture)
        await owner.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_postgres_pool_reuse_does_not_inherit_privileged_scope() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    fixture = await _create_fixture(owner)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection:
            await connection.execute("BEGIN")
            await connection.execute("SET LOCAL ROLE strayhub_runtime")
            await connection.execute(
                "SELECT set_config('app.current_org_id', $1, true)",
                str(fixture.organization_a),
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM organizations WHERE id = $1", fixture.organization_a
                )
                == 1
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM organizations WHERE id = $1", fixture.organization_b
                )
                == 0
            )
            await connection.execute("SELECT set_config('app.platform_scope', 'true', true)")
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM care_reports WHERE organization_id = ANY($1::uuid[])",
                    [
                        fixture.organization_a,
                        fixture.organization_b,
                        fixture.organization_c,
                    ],
                )
                == 3
            )
            await connection.execute("COMMIT")

        async with pool.acquire() as connection:
            await connection.execute("BEGIN")
            await connection.execute("SET LOCAL ROLE strayhub_runtime")
            assert not await connection.fetchval(
                "SELECT current_setting('app.current_org_id', true)"
            )
            assert await connection.fetchval(
                "SELECT current_setting('app.platform_scope', true)"
            ) in {"", "false"}
            assert await connection.fetchval("SELECT count(*) FROM organizations") == 0
            assert await connection.fetchval("SELECT count(*) FROM care_reports") == 0
            await connection.execute("ROLLBACK")
    finally:
        await pool.close()
        await _delete_fixture(owner, fixture)
        await owner.close()


@pytest.mark.asyncio
async def test_real_postgres_scope_helpers_clear_platform_support_flag() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    engine = _runtime_engine(database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    organization_id = uuid4()
    try:
        await owner.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Scope flag test', $2, 'active', now(), now())
            """,
            organization_id,
            f"RLS-FLAG-{organization_id.hex[:10]}",
        )
        async with maker() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
                await set_platform_support_scope(session, organization_id)
                assert (
                    await session.scalar(
                        text("SELECT current_setting('app.platform_support', true)")
                    )
                    == "true"
                )
                await set_organization_scope(session, organization_id)
                flags = await session.execute(
                    text(
                        "SELECT current_setting('app.current_org_id', true), "
                        "current_setting('app.platform_scope', true), "
                        "current_setting('app.platform_support', true), "
                        "current_setting('app.auth_user_id', true), "
                        "current_setting('app.auth_exact_org_id', true), "
                        "current_setting('app.public_volunteer_directory', true)"
                    )
                )
                assert flags.one() == (
                    str(organization_id),
                    "false",
                    "false",
                    "",
                    "",
                    "false",
                )
                await set_platform_support_scope(session, organization_id)
                await set_platform_scope(session)
                flags = await session.execute(
                    text(
                        "SELECT current_setting('app.current_org_id', true), "
                        "current_setting('app.platform_scope', true), "
                        "current_setting('app.platform_support', true), "
                        "current_setting('app.auth_user_id', true), "
                        "current_setting('app.auth_exact_org_id', true), "
                        "current_setting('app.public_volunteer_directory', true)"
                    )
                )
                assert flags.one() == ("", "true", "false", "", "", "false")
    finally:
        await owner.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await owner.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_postgres_summary_denies_unauthorized_callers() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    engine = _runtime_engine(database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fixture = await _create_fixture(owner)
    try:
        async with maker() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
                await set_organization_scope(session, fixture.organization_a)
                access_repository = VolunteerAccessRepository(session, fixture.organization_a)
                summary_repository = VolunteerServiceSummaryRepository(
                    session, fixture.organization_a
                )
                service = VolunteerServiceSummaryService(
                    access_repository,
                    summary_repository,
                    audit=AuditService(session),
                )
                denied_contexts = (
                    TenantContext(
                        fixture.inactive_reviewer,
                        fixture.organization_a,
                        "SHELTER_ADMIN",
                    ),
                    TenantContext(fixture.reviewer_a, fixture.organization_b, "SHELTER_ADMIN"),
                    TenantContext(fixture.reviewer_a, fixture.organization_a, "VOLUNTEER"),
                    TenantContext(fixture.reviewer_a, None, "PLATFORM_ADMIN", platform_scope=True),
                )
                for context in denied_contexts:
                    with pytest.raises(DomainError) as error:
                        await service.for_application(
                            fixture.application_x,
                            tenant_context=context,
                            purpose_code=SUMMARY_PURPOSE,
                            cursor=None,
                            cursor_secret="real-rls-test-secret",
                            limit=100,
                        )
                    assert error.value.status_code == 403
    finally:
        await _delete_fixture(owner, fixture)
        await owner.close()
        await engine.dispose()
