import os
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_pii_service import VolunteerPiiService
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.infrastructure.security.pii_cipher import AesGcmPiiCipher
from services.api.app.infrastructure.security.pii_reveal_audit import (
    TransactionalPiiCollectionAuditor,
)
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _database_url() -> str:
    value = os.environ.get("STRAYHUB_TEST_DATABASE_URL")
    if not value:
        raise RuntimeError("STRAYHUB_TEST_DATABASE_URL is required for PostgreSQL isolation tests")
    return value


@pytest.mark.asyncio
async def test_runtime_repository_persists_and_reads_encrypted_profile() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    organization_id = uuid4()
    user_id = uuid4()
    membership_id = uuid4()
    application_id = uuid4()
    rollback_application_id = uuid4()
    collection_request_id = uuid4()
    sentinel_name = "測試志工ORM"
    sentinel_phone = "0900000099"
    sentinel_identity = "A123456789"
    now = datetime.now(timezone.utc)
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = VolunteerPiiService(
        AesGcmPiiCipher(keys={"test-v1": bytes(range(32))}, active_key_version="test-v1")
    )

    try:
        await owner.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'PII ORM shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"PII-ORM-{organization_id.hex[:8]}",
        )
        await owner.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'PII ORM applicant', 'active', now(), now())
            """,
            user_id,
            f"pii-orm-{user_id.hex[:8]}",
        )
        await owner.execute(
            """
            INSERT INTO organization_volunteer_access_policies
              (organization_id, applications_enabled, insurance_required,
               default_grant_duration_hours, version)
            VALUES ($1, true, true, 168, 3)
            """,
            organization_id,
        )
        await owner.execute(
            """
            INSERT INTO organization_memberships
              (id, organization_id, user_id, role, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'SHELTER_ADMIN', 'active', now(), now())
            """,
            membership_id,
            organization_id,
            user_id,
        )
        await owner.execute(
            """
            INSERT INTO volunteer_applications
              (id, organization_id, user_id, status, source_channel,
               submitted_at, created_at, updated_at)
            VALUES ($1, $2, $3, 'pending', 'liff', now(), now(), now())
            """,
            application_id,
            organization_id,
            user_id,
        )
        await owner.execute(
            """
            INSERT INTO volunteer_applications
              (id, organization_id, user_id, status, source_channel,
               submitted_at, withdrawn_at, created_at, updated_at)
            VALUES ($1, $2, $3, 'withdrawn', 'liff', now(), now(), now(), now())
            """,
            rollback_application_id,
            organization_id,
            user_id,
        )

        async with maker() as session:
            await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
            await set_organization_scope(session, organization_id)
            repository = VolunteerAccessRepository(session, organization_id)
            create_service = VolunteerPiiService(
                AesGcmPiiCipher(keys={"test-v1": bytes(range(32))}, active_key_version="test-v1"),
                collection_auditor=TransactionalPiiCollectionAuditor(),
            )
            await create_service.create_profile(
                repository=repository,
                application_id=application_id,
                applicant_name=sentinel_name,
                phone_number=sentinel_phone,
                basic_profile={"experience": "ORM測試"},
                insurance_identity=sentinel_identity,
                insurance_consent_acknowledged=True,
                insurance_collection_mode="strayhub_temporary",
                insurance_purpose_code="insurance_verification",
                insurance_policy_version="organization-policy-v3",
                request_id=collection_request_id,
                now=now,
            )
            await session.commit()

        raw = await owner.fetchrow(
            """
            SELECT applicant_name_ciphertext, phone_ciphertext, basic_profile_ciphertext,
                   insurance_identity_ciphertext
            FROM volunteer_application_profiles
            WHERE application_id = $1
            """,
            application_id,
        )
        assert raw is not None
        stored_payload = b"".join(raw)
        assert sentinel_name.encode() not in stored_payload
        assert sentinel_phone.encode() not in stored_payload
        assert sentinel_identity.encode() not in stored_payload

        audit_row = await owner.fetchrow(
            """
            SELECT action, actor_user_id, after_data
            FROM audit_records
            WHERE organization_id = $1 AND resource_id = $2
              AND action = 'insurance_identity.submitted'
            """,
            organization_id,
            application_id,
        )
        assert audit_row is not None
        assert audit_row["actor_user_id"] == user_id
        audit_payload = repr(audit_row["after_data"])
        assert "insurance_verification" in audit_payload
        assert "organization-policy-v3" in audit_payload
        assert "APPLICANT" in audit_payload
        assert str(collection_request_id) in audit_payload
        assert sentinel_identity not in audit_payload
        assert "ciphertext" not in audit_payload

        async with maker() as session:
            await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
            await set_organization_scope(session, uuid4())
            hidden = await session.execute(
                text(
                    "SELECT id FROM audit_records "
                    "WHERE organization_id = :organization_id AND resource_id = :application_id"
                ),
                {"organization_id": organization_id, "application_id": application_id},
            )
            assert hidden.first() is None

        async with maker() as session:

            class WrongScopeCollectionAuditor(TransactionalPiiCollectionAuditor):
                async def persist_atomic_collection(self, event, *, transaction) -> None:
                    await set_organization_scope(transaction, uuid4())
                    await super().persist_atomic_collection(event, transaction=transaction)

            await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
            await set_organization_scope(session, organization_id)
            repository = VolunteerAccessRepository(session, organization_id)
            failing_service = VolunteerPiiService(
                AesGcmPiiCipher(keys={"test-v1": bytes(range(32))}, active_key_version="test-v1"),
                collection_auditor=WrongScopeCollectionAuditor(),
            )
            with pytest.raises(DomainError) as error:
                await failing_service.create_profile(
                    repository=repository,
                    application_id=rollback_application_id,
                    applicant_name="不得保存",
                    phone_number="0900000088",
                    basic_profile=None,
                    insurance_identity="B123456789",
                    insurance_consent_acknowledged=True,
                    insurance_collection_mode="strayhub_temporary",
                    insurance_purpose_code="insurance_verification",
                    insurance_policy_version="organization-policy-v3",
                    request_id=uuid4(),
                    now=now,
                )
            assert error.value.code == "pii_audit_unavailable"

        assert (
            await owner.fetchval(
                "SELECT count(*) FROM volunteer_application_profiles WHERE application_id = $1",
                rollback_application_id,
            )
            == 0
        )
        assert (
            await owner.fetchval(
                "SELECT count(*) FROM audit_records WHERE resource_id = $1",
                rollback_application_id,
            )
            == 0
        )

        async with maker() as session:

            class CaptureAudit:
                called = False

                async def persist_committed_reveal(self, event) -> None:
                    self.called = True

            await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
            await set_organization_scope(session, organization_id)
            repository = VolunteerAccessRepository(session, organization_id)
            audit = CaptureAudit()
            revealed = await service.reveal_profile(
                repository=repository,
                application_id=application_id,
                tenant_context=TenantContext(
                    user_id=user_id,
                    organization_id=organization_id,
                    role="STAFF",
                ),
                purpose_code="application_review",
                request_id=uuid4(),
                policy_version="volunteer-pii-v1",
                now=now,
                audit=audit,
            )
            assert audit.called is True
            assert revealed.applicant_name == sentinel_name
            assert revealed.phone_number == sentinel_phone
    finally:
        await owner.execute(
            "DELETE FROM audit_records WHERE resource_id = $1",
            application_id,
        )
        await owner.execute(
            "DELETE FROM volunteer_application_profiles WHERE application_id = $1",
            application_id,
        )
        await owner.execute("DELETE FROM volunteer_applications WHERE id = $1", application_id)
        await owner.execute(
            "DELETE FROM volunteer_applications WHERE id = $1",
            rollback_application_id,
        )
        await owner.execute(
            "DELETE FROM organization_volunteer_access_policies WHERE organization_id = $1",
            organization_id,
        )
        await owner.execute("DELETE FROM organization_memberships WHERE id = $1", membership_id)
        await owner.execute("DELETE FROM users WHERE id = $1", user_id)
        await owner.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await owner.close()
        await engine.dispose()
