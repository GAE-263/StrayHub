from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import asyncpg
import pytest
from services.api.app.api.animal_selection import (
    QrCandidateOrganizationRequest,
    authorize_qr_candidate_organization,
)
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import (
    AnimalSelectionService,
    issue_animal_confirmation_token,
)
from services.api.app.application.care_report_handoff_service import CareReportHandoffService
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.care_report_handoff import CareReportHandoff
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.care_report_handoff_repository import (
    CareReportHandoffRepository,
)
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


def _async_database_url() -> str:
    return _database_url().replace("postgresql://", "postgresql+asyncpg://", 1)


async def _set_platform(connection) -> None:
    await connection.execute("SELECT set_config('app.platform_scope', 'true', true)")
    await connection.execute("SELECT set_config('app.current_org_id', '', true)")
    await connection.execute("SELECT set_config('app.auth_user_id', '', true)")


async def _setup_fixture() -> SimpleNamespace:
    ids = SimpleNamespace(
        organization_a=uuid4(),
        organization_b=uuid4(),
        user=uuid4(),
        membership_a=uuid4(),
        membership_b=uuid4(),
        application_a=uuid4(),
        application_b=uuid4(),
        grant_a=uuid4(),
        grant_b=uuid4(),
        animal_a=uuid4(),
        animal_b=uuid4(),
        qr_a=uuid4(),
        qr_b=uuid4(),
        qr_token_a=f"handoff-qr-a-{uuid4().hex}",
        qr_token_b=f"handoff-qr-b-{uuid4().hex}",
        handoff_a=uuid4(),
    )
    connection = await asyncpg.connect(_database_url())
    now = datetime.now(timezone.utc)
    try:
        await connection.execute("BEGIN")
        await _set_platform(connection)
        for organization_id, suffix in (
            (ids.organization_a, "A"),
            (ids.organization_b, "B"),
        ):
            code = f"HANDOFF-{suffix}-{organization_id.hex[:10]}"
            await connection.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', now(), now())
                """,
                organization_id,
                code,
                code,
            )
        await connection.execute(
            """
            INSERT INTO users (id, display_name, status, created_at, updated_at)
            VALUES ($1, 'Handoff Volunteer', 'active', now(), now())
            """,
            ids.user,
        )
        for organization_id, membership_id in (
            (ids.organization_a, ids.membership_a),
            (ids.organization_b, ids.membership_b),
        ):
            await connection.execute(
                """
                INSERT INTO organization_memberships
                    (id, organization_id, user_id, role, status, valid_from, expires_at,
                     access_version, medical_care_access, created_at, updated_at)
                VALUES ($1, $2, $3, 'VOLUNTEER', 'active', $4, $5, 0, false, now(), now())
                """,
                membership_id,
                organization_id,
                ids.user,
                now - timedelta(hours=1),
                now + timedelta(hours=2),
            )
        for organization_id, application_id, grant_id, membership_id in (
            (
                ids.organization_a,
                ids.application_a,
                ids.grant_a,
                ids.membership_a,
            ),
            (
                ids.organization_b,
                ids.application_b,
                ids.grant_b,
                ids.membership_b,
            ),
        ):
            await connection.execute(
                """
                INSERT INTO volunteer_applications
                    (id, organization_id, user_id, status, source_channel, submitted_at,
                     decided_at, version, created_at, updated_at)
                VALUES ($1, $2, $3, 'approved', 'liff', $4, $4, 1, now(), now())
                """,
                application_id,
                organization_id,
                ids.user,
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
                ids.user,
                membership_id,
                application_id,
                now - timedelta(hours=1),
                now + timedelta(hours=2),
            )
        for organization_id, animal_id, qr_id, qr_token in (
            (ids.organization_a, ids.animal_a, ids.qr_a, ids.qr_token_a),
            (ids.organization_b, ids.animal_b, ids.qr_b, ids.qr_token_b),
        ):
            await connection.execute(
                """
                INSERT INTO animals
                    (id, organization_id, name, status, created_at, updated_at)
                VALUES ($1, $2, 'Handoff Animal', 'active', now(), now())
                """,
                animal_id,
                organization_id,
            )
            await connection.execute(
                """
                INSERT INTO animal_qr_codes
                    (id, organization_id, animal_id, token_digest, status, revoked,
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, 'active', false, now(), now())
                """,
                qr_id,
                organization_id,
                animal_id,
                hashlib.sha256(qr_token.encode()).hexdigest(),
            )
        await connection.execute(
            """
            INSERT INTO care_report_handoffs
                (id, organization_id, user_id, membership_id, animal_id, status,
                 expires_at, source, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, 'pending', $6, 'liff_scan', $7, $7)
            """,
            ids.handoff_a,
            ids.organization_a,
            ids.user,
            ids.membership_a,
            ids.animal_a,
            now + timedelta(minutes=15),
            now,
        )
        await connection.execute("COMMIT")
        return ids
    except Exception:
        await connection.execute("ROLLBACK")
        raise
    finally:
        await connection.close()


async def _cleanup_fixture(ids: SimpleNamespace) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await _set_platform(connection)
        organizations = [ids.organization_a, ids.organization_b]
        await connection.execute(
            "DELETE FROM care_report_handoffs WHERE organization_id = ANY($1::uuid[])",
            organizations,
        )
        await connection.execute(
            "DELETE FROM animal_qr_codes WHERE organization_id = ANY($1::uuid[])", organizations
        )
        await connection.execute(
            "DELETE FROM volunteer_access_grants WHERE organization_id = ANY($1::uuid[])",
            organizations,
        )
        await connection.execute(
            "DELETE FROM volunteer_applications WHERE organization_id = ANY($1::uuid[])",
            organizations,
        )
        await connection.execute(
            "DELETE FROM organization_memberships WHERE organization_id = ANY($1::uuid[])",
            organizations,
        )
        await connection.execute(
            "DELETE FROM animals WHERE organization_id = ANY($1::uuid[])",
            organizations,
        )
        await connection.execute("DELETE FROM users WHERE id = $1", ids.user)
        await connection.execute(
            "DELETE FROM organizations WHERE id = ANY($1::uuid[])",
            organizations,
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


def _service(session, organization_id: UUID) -> CareReportHandoffService:
    animals = AnimalRepository(session, organization_id)
    return CareReportHandoffService(
        CareReportHandoffRepository(session, organization_id),
        authorization=VolunteerReportingAuthorizationService(
            AuthenticationRepository(session), animals
        ),
    )


def _selection_service(session, organization_id: UUID) -> AnimalSelectionService:
    animals = AnimalRepository(session, organization_id)
    return AnimalSelectionService(
        animals,
        QrCodeRepository(session, organization_id),
        VolunteerReportingAuthorizationService(AuthenticationRepository(session), animals),
    )


@pytest.mark.asyncio
async def test_real_postgres_cross_shelter_qr_preflight_is_authorized_and_restores_scope() -> None:
    ids = await _setup_fixture()
    engine = create_async_engine(_async_database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    context = RequestContext(
        user_id=ids.user,
        organization_id=ids.organization_a,
        membership_id=ids.membership_a,
        role="VOLUNTEER",
        session_id=uuid4(),
    )
    try:
        async with sessions() as session:
            async with session.begin():
                await set_organization_scope(session, ids.organization_a)
                response = await authorize_qr_candidate_organization(
                    QrCandidateOrganizationRequest(
                        qr_token=ids.qr_token_b,
                        candidate_organization_id=ids.organization_b,
                    ),
                    context,
                    session,
                )
                assert response.organization_id == ids.organization_b
                assert response.model_dump().keys() == {
                    "organization_id",
                    "organization_name",
                }
                animals_a = AnimalRepository(session, ids.organization_a)
                assert await animals_a.get(ids.animal_a) is not None
                assert await animals_a.get(ids.animal_b) is None

        connection = await asyncpg.connect(_database_url())
        try:
            await connection.execute("BEGIN")
            await _set_platform(connection)
            await connection.execute(
                "UPDATE volunteer_access_grants "
                "SET expires_at = now() - interval '1 minute' WHERE id = $1",
                ids.grant_b,
            )
            await connection.execute("COMMIT")
        finally:
            await connection.close()

        async with sessions() as session:
            async with session.begin():
                await set_organization_scope(session, ids.organization_a)
                with pytest.raises(DomainError):
                    await authorize_qr_candidate_organization(
                        QrCandidateOrganizationRequest(
                            qr_token=ids.qr_token_b,
                            candidate_organization_id=ids.organization_b,
                        ),
                        context,
                        session,
                    )
    finally:
        await engine.dispose()
        await _cleanup_fixture(ids)


@pytest.mark.asyncio
async def test_real_postgres_scope_free_qr_confirm_handoff_create_and_consume() -> None:
    ids = await _setup_fixture()
    engine = create_async_engine(_async_database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    session_id = uuid4()
    try:
        async with sessions() as session:
            async with session.begin():
                await set_organization_scope(session, ids.organization_a)
                selection = _selection_service(session, ids.organization_a)
                candidate = await selection.resolve_qr(
                    raw_token=ids.qr_token_a,
                    user_id=ids.user,
                    organization_id=ids.organization_a,
                    membership_id=ids.membership_a,
                    role="VOLUNTEER",
                )
                assert candidate.animal.id == ids.animal_a
                confirmed = await selection.confirm(
                    animal_id=ids.animal_a,
                    user_id=ids.user,
                    organization_id=ids.organization_a,
                    membership_id=ids.membership_a,
                    role="VOLUNTEER",
                )
                assert confirmed.animal.id == ids.animal_a
                with pytest.raises(DomainError) as cross_tenant:
                    await selection.resolve_qr(
                        raw_token=ids.qr_token_b,
                        user_id=ids.user,
                        organization_id=ids.organization_a,
                        membership_id=ids.membership_a,
                        role="VOLUNTEER",
                    )
                assert cross_tenant.value.code == "animal_not_found"

                confirmation_token = issue_animal_confirmation_token(
                    user_id=ids.user,
                    organization_id=ids.organization_a,
                    membership_id=ids.membership_a,
                    session_id=session_id,
                    animal_id=ids.animal_a,
                )
                handoff = await _service(session, ids.organization_a).create_or_replace_handoff(
                    user_id=ids.user,
                    organization_id=ids.organization_a,
                    membership_id=ids.membership_a,
                    session_id=session_id,
                    animal_id=ids.animal_a,
                    confirmation_token=confirmation_token,
                    source="liff_scan",
                )
                assert handoff.status == "pending"

        async with sessions() as session:
            async with session.begin():
                await set_organization_scope(session, ids.organization_a)
                consumed = await _service(session, ids.organization_a).consume_pending_handoff(
                    user_id=ids.user,
                    organization_id=ids.organization_a,
                )
                assert consumed.status == "consumed"

        connection = await asyncpg.connect(_database_url())
        try:
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM daily_reportable_scopes WHERE organization_id = $1",
                    ids.organization_a,
                )
                == 0
            )
        finally:
            await connection.close()
    finally:
        await engine.dispose()
        await _cleanup_fixture(ids)


@pytest.mark.asyncio
async def test_real_postgres_tenant_scope_and_user_bound_replace() -> None:
    ids = await _setup_fixture()
    engine = create_async_engine(_async_database_url(), pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            async with session.begin():
                await set_organization_scope(session, ids.organization_b)
                repository = CareReportHandoffRepository(session, ids.organization_b)
                assert await repository.lock_pending_for_user(ids.user) is None
                now = datetime.now(timezone.utc)
                await repository.replace_pending(
                    CareReportHandoff(
                        organization_id=ids.organization_b,
                        user_id=ids.user,
                        membership_id=ids.membership_b,
                        animal_id=ids.animal_b,
                        status="pending",
                        source="qr_deeplink",
                        created_at=now,
                        updated_at=now,
                        expires_at=now + timedelta(minutes=15),
                    ),
                    now=now,
                )

        connection = await asyncpg.connect(_database_url())
        try:
            await connection.execute("BEGIN")
            await _set_platform(connection)
            rows = await connection.fetch(
                """
                SELECT organization_id, status
                FROM care_report_handoffs
                WHERE user_id = $1
                ORDER BY created_at
                """,
                ids.user,
            )
            assert [(row["organization_id"], row["status"]) for row in rows] == [
                (ids.organization_a, "superseded"),
                (ids.organization_b, "pending"),
            ]
            await connection.execute("ROLLBACK")
        finally:
            await connection.close()
    finally:
        await engine.dispose()
        await _cleanup_fixture(ids)


@pytest.mark.asyncio
async def test_real_postgres_concurrent_consume_allows_exactly_one_winner() -> None:
    ids = await _setup_fixture()
    engine = create_async_engine(_async_database_url(), pool_size=2, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def consume():
        async with sessions() as session:
            async with session.begin():
                await set_organization_scope(session, ids.organization_a)
                return await _service(session, ids.organization_a).consume_pending_handoff(
                    user_id=ids.user,
                    organization_id=ids.organization_a,
                )

    try:
        results = await asyncio.gather(consume(), consume(), return_exceptions=True)
        successes = [result for result in results if isinstance(result, CareReportHandoff)]
        failures = [result for result in results if isinstance(result, DomainError)]

        assert len(successes) == 1
        assert successes[0].status == "consumed"
        assert len(failures) == 1
        assert failures[0].code == "handoff_already_consumed"
    finally:
        await engine.dispose()
        await _cleanup_fixture(ids)


@pytest.mark.asyncio
async def test_real_postgres_rls_and_pool_reuse_do_not_leak_tenant_scope() -> None:
    ids = await _setup_fixture()
    pool = await asyncpg.create_pool(_database_url(), min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SET ROLE strayhub_runtime")
                await connection.execute(
                    "SELECT set_config('app.current_org_id', $1, true)",
                    str(ids.organization_a),
                )
                assert (
                    await connection.fetchval(
                        "SELECT id FROM care_report_handoffs WHERE id = $1",
                        ids.handoff_a,
                    )
                    == ids.handoff_a
                )

        async with pool.acquire() as reused:
            async with reused.transaction():
                await reused.execute("SET ROLE strayhub_runtime")
                await reused.execute(
                    "SELECT set_config('app.current_org_id', $1, true)",
                    str(ids.organization_b),
                )
                assert (
                    await reused.fetchval(
                        "SELECT id FROM care_report_handoffs WHERE id = $1",
                        ids.handoff_a,
                    )
                    is None
                )
    finally:
        await pool.close()
        await _cleanup_fixture(ids)
