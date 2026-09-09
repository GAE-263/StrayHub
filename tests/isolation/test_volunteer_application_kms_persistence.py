import os
from datetime import date, timedelta
from uuid import uuid4

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from services.api.app.api.dependencies import request_session
from services.api.app.api.volunteer_access import (
    get_line_identity_verifier,
    get_volunteer_pii_service,
)
from services.api.app.application.volunteer_pii_service import VolunteerPiiService
from services.api.app.infrastructure.security.pii_cipher import AesGcmPiiCipher
from services.api.app.main import app
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

KMS_KEY_VERSION = (
    "projects/acceptance-project/locations/asia-east1/keyRings/strayhub-pii/"
    "cryptoKeys/volunteer-application-profile/cryptoKeyVersions/1"
)


class _Verifier:
    def __init__(self, line_user_id: str) -> None:
        self.line_user_id = line_user_id

    async def verify(self, token: str) -> str:
        assert token == "synthetic-id-token"
        return self.line_user_id


class _FailingProfileService:
    async def create_profile(self, *, repository, **_kwargs) -> None:
        await repository.session.execute(text("SELECT 1 / 0"))


def _database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


def _payload(organization_id, client_request_id) -> dict:
    return {
        "id_token": "synthetic-id-token",
        "organization_id": str(organization_id),
        "applicant_name": "Synthetic Applicant",
        "phone_number": "0900000000",
        "client_request_id": str(client_request_id),
        "consent_acknowledged": True,
        "service_dates": [(date.today() + timedelta(days=1)).isoformat()],
    }


@pytest.mark.asyncio
async def test_unaffiliated_submission_persists_full_kms_version_and_rejects_duplicates() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    organization_id = uuid4()
    line_user_id = f"U-kms-profile-{uuid4().hex}"
    first_request_id = uuid4()
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        await owner.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'KMS profile shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"KMS-PROFILE-{organization_id.hex[:10]}",
        )
        await owner.execute(
            """
            INSERT INTO organization_volunteer_access_policies
              (organization_id, applications_enabled, insurance_required,
               default_grant_duration_hours, daily_application_limit, version)
            VALUES ($1, true, false, 168, 20, 1)
            """,
            organization_id,
        )

        async with maker() as session:
            app.dependency_overrides[request_session] = lambda: session
            app.dependency_overrides[get_line_identity_verifier] = lambda: _Verifier(line_user_id)
            app.dependency_overrides[get_volunteer_pii_service] = lambda: VolunteerPiiService(
                AesGcmPiiCipher(
                    keys={KMS_KEY_VERSION: bytes(range(32))},
                    active_key_version=KMS_KEY_VERSION,
                )
            )
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                first = await client.post(
                    "/v1/volunteer-applications",
                    json=_payload(organization_id, first_request_id),
                )
                replay = await client.post(
                    "/v1/volunteer-applications",
                    json=_payload(organization_id, uuid4()),
                )

        assert first.status_code == 201
        assert first.json()["effective_status"] == "pending"
        assert replay.status_code == 200
        assert replay.json()["application"]["id"] == first.json()["application"]["id"]
        rows = await owner.fetch(
            """
            SELECT application.id, application.status, profile.encryption_key_version
            FROM volunteer_applications AS application
            JOIN line_user_bindings AS binding ON binding.user_id = application.user_id
            JOIN volunteer_application_profiles AS profile
              ON profile.organization_id = application.organization_id
             AND profile.application_id = application.id
            WHERE application.organization_id = $1 AND binding.line_user_id = $2
            """,
            organization_id,
            line_user_id,
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert rows[0]["encryption_key_version"] == KMS_KEY_VERSION
        assert len(KMS_KEY_VERSION) > 80
        assert (
            await owner.fetchval(
                """
                SELECT count(*)
                FROM organization_memberships AS membership
                JOIN line_user_bindings AS binding ON binding.user_id = membership.user_id
                WHERE membership.organization_id = $1 AND binding.line_user_id = $2
                """,
                organization_id,
                line_user_id,
            )
            == 0
        )
    finally:
        app.dependency_overrides.clear()
        user_id = await owner.fetchval(
            "SELECT user_id FROM line_user_bindings WHERE line_user_id = $1", line_user_id
        )
        if user_id is not None:
            await owner.execute(
                "DELETE FROM audit_records WHERE organization_id = $1", organization_id
            )
            await owner.execute(
                "DELETE FROM volunteer_notification_deliveries WHERE organization_id = $1",
                organization_id,
            )
            await owner.execute(
                "DELETE FROM volunteer_application_service_dates WHERE organization_id = $1",
                organization_id,
            )
            await owner.execute(
                "DELETE FROM volunteer_application_profiles WHERE organization_id = $1",
                organization_id,
            )
            await owner.execute(
                "DELETE FROM volunteer_applications WHERE organization_id = $1", organization_id
            )
            await owner.execute(
                "DELETE FROM line_user_bindings WHERE line_user_id = $1", line_user_id
            )
            await owner.execute("DELETE FROM users WHERE id = $1", user_id)
        await owner.execute(
            "DELETE FROM organization_volunteer_access_policies WHERE organization_id = $1",
            organization_id,
        )
        await owner.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await owner.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_profile_database_failure_rolls_back_identity_and_application() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    organization_id = uuid4()
    line_user_id = f"U-kms-rollback-{uuid4().hex}"
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        await owner.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'KMS rollback shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"KMS-ROLLBACK-{organization_id.hex[:10]}",
        )
        await owner.execute(
            """
            INSERT INTO organization_volunteer_access_policies
              (organization_id, applications_enabled, insurance_required,
               default_grant_duration_hours, daily_application_limit, version)
            VALUES ($1, true, false, 168, 20, 1)
            """,
            organization_id,
        )
        async with maker() as session:
            app.dependency_overrides[request_session] = lambda: session
            app.dependency_overrides[get_line_identity_verifier] = lambda: _Verifier(line_user_id)
            app.dependency_overrides[get_volunteer_pii_service] = lambda: _FailingProfileService()
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/v1/volunteer-applications",
                    json=_payload(organization_id, uuid4()),
                )
            await session.rollback()

        assert response.status_code == 503
        assert response.json()["code"] == "internal_error"
        assert "LINE" not in response.json()["message"]
        assert (
            await owner.fetchval(
                """
                SELECT count(*) FROM volunteer_applications
                WHERE organization_id = $1
                """,
                organization_id,
            )
            == 0
        )
        assert (
            await owner.fetchval(
                """
                SELECT count(*) FROM volunteer_application_profiles
                WHERE organization_id = $1
                """,
                organization_id,
            )
            == 0
        )
        assert (
            await owner.fetchval(
                "SELECT count(*) FROM line_user_bindings WHERE line_user_id = $1",
                line_user_id,
            )
            == 0
        )
    finally:
        app.dependency_overrides.clear()
        await owner.execute(
            "DELETE FROM organization_volunteer_access_policies WHERE organization_id = $1",
            organization_id,
        )
        await owner.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await owner.close()
        await engine.dispose()
