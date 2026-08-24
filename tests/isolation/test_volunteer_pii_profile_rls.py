import os
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.application.volunteer_pii_service import VolunteerPiiService
from services.api.app.infrastructure.security.pii_cipher import AesGcmPiiCipher
from services.api.app.persistence.models.volunteer_access import (
    VolunteerApplication,
    VolunteerApplicationProfile,
)


def _database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


@pytest.mark.asyncio
async def test_real_postgres_pii_profiles_are_isolated_from_other_and_public_scopes() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    user_id = uuid4()
    application_a = uuid4()
    application_b = uuid4()
    try:
        await connection.execute("BEGIN")
        for organization_id, code in (
            (organization_a, f"PII-A-{organization_a.hex[:10]}"),
            (organization_b, f"PII-B-{organization_b.hex[:10]}"),
        ):
            await connection.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $2, 'active', now(), now())
                """,
                organization_id,
                code,
            )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'LINE 志工', 'active', now(), now())
            """,
            user_id,
            f"pii-profile-{user_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO volunteer_applications
              (id, organization_id, user_id, status, source_channel,
               submitted_at, created_at, updated_at)
            VALUES
              ($1, $2, $3, 'pending', 'liff', now(), now(), now()),
              ($4, $5, $3, 'pending', 'liff', now(), now(), now())
            """,
            application_a,
            organization_a,
            user_id,
            application_b,
            organization_b,
        )
        await connection.execute(
            """
            INSERT INTO volunteer_application_profiles
              (application_id, organization_id, applicant_name_ciphertext,
               phone_ciphertext, pii_schema_version, encryption_algorithm, encryption_key_version,
               retention_expires_at, created_at, updated_at)
            VALUES
              ($1, $2, $3, $4, 'v1', 'AES-256-GCM', 'local-v1',
               now() + interval '180 days', now(), now()),
              ($5, $6, $7, $8, 'v1', 'AES-256-GCM', 'local-v1',
               now() + interval '180 days', now(), now())
            """,
            application_a,
            organization_a,
            b"cipher-name-a",
            b"cipher-phone-a",
            application_b,
            organization_b,
            b"cipher-name-b",
            b"cipher-phone-b",
        )

        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute(
            "SELECT set_config('app.current_org_id', $1, true)", str(organization_a)
        )
        rows = await connection.fetch(
            "SELECT application_id, organization_id "
            "FROM volunteer_application_profiles ORDER BY application_id"
        )
        assert [(row["application_id"], row["organization_id"]) for row in rows] == [
            (application_a, organization_a)
        ]
        assert (
            await connection.execute(
                "UPDATE volunteer_application_profiles SET updated_at = now() "
                "WHERE application_id = $1",
                application_b,
            )
            == "UPDATE 0"
        )

        await connection.execute("SELECT set_config('app.current_org_id', '', true)")
        await connection.execute("SELECT set_config('app.platform_scope', 'true', true)")
        await connection.execute(
            "SELECT set_config('app.public_volunteer_directory', 'true', true)"
        )
        assert await connection.fetchval("SELECT count(*) FROM volunteer_application_profiles") == 0
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_real_postgres_profile_readback_contains_only_service_ciphertext() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_id = uuid4()
    user_id = uuid4()
    application = VolunteerApplication(
        id=uuid4(),
        organization_id=organization_id,
        user_id=user_id,
    )
    service = VolunteerPiiService(
        AesGcmPiiCipher(
            keys={"test-v1": bytes(range(32))},
            active_key_version="test-v1",
        )
    )
    sentinel_name = "測試志工甲"
    sentinel_phone = "0900000001"
    now = datetime.now(timezone.utc)
    profile = service.build_profile(
        application=application,
        applicant_name=sentinel_name,
        phone_number=sentinel_phone,
        basic_profile={"experience": "測試資料"},
        insurance_identity=None,
        insurance_required=False,
        now=now,
    )
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'PII readback shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"PII-READ-{organization_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'LINE applicant', 'active', now(), now())
            """,
            user_id,
            f"pii-read-{user_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO volunteer_applications
              (id, organization_id, user_id, status, source_channel,
               submitted_at, created_at, updated_at)
            VALUES ($1, $2, $3, 'pending', 'liff', now(), now(), now())
            """,
            application.id,
            organization_id,
            user_id,
        )
        await connection.execute(
            """
            INSERT INTO volunteer_application_profiles
              (application_id, organization_id, applicant_name_ciphertext,
               phone_ciphertext, basic_profile_ciphertext, pii_schema_version, encryption_algorithm,
               encryption_key_version, retention_expires_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
            """,
            profile.application_id,
            profile.organization_id,
            profile.applicant_name_ciphertext,
            profile.phone_ciphertext,
            profile.basic_profile_ciphertext,
            profile.pii_schema_version,
            profile.encryption_algorithm,
            profile.encryption_key_version,
            profile.retention_expires_at,
            now,
        )
        row = await connection.fetchrow(
            "SELECT * FROM volunteer_application_profiles WHERE application_id = $1",
            application.id,
        )
        assert row is not None
        stored_payload = b"".join(
            row[column]
            for column in (
                "applicant_name_ciphertext",
                "phone_ciphertext",
                "basic_profile_ciphertext",
            )
        )
        assert sentinel_name.encode() not in stored_payload
        assert sentinel_phone.encode() not in stored_payload
        stored_profile = VolunteerApplicationProfile(
            **{
                column: row[column]
                for column in VolunteerApplicationProfile.__table__.columns.keys()
            }
        )
        revealed = service._decrypt_profile(
            stored_profile,
            organization_id=organization_id,
            application_id=application.id,
            now=now,
        )
        assert revealed.applicant_name == sentinel_name
        assert revealed.phone_number == sentinel_phone
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_real_postgres_rejects_cross_scope_profile_and_overlong_insurance_retention() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    user_id = uuid4()
    application_id = uuid4()
    try:
        await connection.execute("BEGIN")
        for organization_id, code in (
            (organization_a, f"PII-CON-A-{organization_a.hex[:8]}"),
            (organization_b, f"PII-CON-B-{organization_b.hex[:8]}"),
        ):
            await connection.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $2, 'active', now(), now())
                """,
                organization_id,
                code,
            )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'PII constraint user', 'active', now(), now())
            """,
            user_id,
            f"pii-constraint-{user_id.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO volunteer_applications
              (id, organization_id, user_id, status, source_channel,
               submitted_at, created_at, updated_at)
            VALUES ($1, $2, $3, 'pending', 'liff', now(), now(), now())
            """,
            application_id,
            organization_a,
            user_id,
        )

        await connection.execute("SAVEPOINT cross_scope_profile")
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await connection.execute(
                """
                INSERT INTO volunteer_application_profiles
                  (application_id, organization_id, applicant_name_ciphertext,
                   phone_ciphertext, pii_schema_version, encryption_algorithm,
                   encryption_key_version,
                   retention_expires_at, created_at, updated_at)
                VALUES ($1, $2, 'name', 'phone', 'v1', 'AES-256-GCM', 'test-v1',
                        now() + interval '180 days', now(), now())
                """,
                application_id,
                organization_b,
            )
        await connection.execute("ROLLBACK TO SAVEPOINT cross_scope_profile")

        await connection.execute("SAVEPOINT overlong_insurance")
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                """
                INSERT INTO volunteer_application_profiles
                  (application_id, organization_id, applicant_name_ciphertext,
                   phone_ciphertext, insurance_identity_ciphertext,
                   pii_schema_version, encryption_algorithm, encryption_key_version,
                   retention_expires_at,
                   insurance_identity_delete_after, created_at, updated_at)
                VALUES ($1, $2, 'name', 'phone', 'identity', 'v1', 'AES-256-GCM', 'test-v1',
                        now() + interval '180 days', now() + interval '31 days', now(), now())
                """,
                application_id,
                organization_a,
            )
        await connection.execute("ROLLBACK TO SAVEPOINT overlong_insurance")
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()
