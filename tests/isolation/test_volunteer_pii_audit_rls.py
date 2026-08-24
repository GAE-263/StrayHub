import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.application.ports.pii import PiiRevealAuditEvent
from services.api.app.infrastructure.security.pii_reveal_audit import CommittedPiiRevealAuditor
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _database_url() -> str:
    value = os.environ.get("STRAYHUB_TEST_DATABASE_URL")
    if not value:
        raise RuntimeError("STRAYHUB_TEST_DATABASE_URL is required for PostgreSQL isolation tests")
    return value


@pytest.mark.asyncio
async def test_committed_reveal_auditor_writes_under_runtime_tenant_scope() -> None:
    database_url = _database_url()
    owner = await asyncpg.connect(database_url)
    organization_id = uuid4()
    other_organization_id = uuid4()
    actor_user_id = uuid4()
    application_id = uuid4()
    request_id = uuid4()
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def runtime_session():
        async with maker() as session:
            await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
            yield session

    try:
        for tenant_id, code in (
            (organization_id, f"PII-AUDIT-{organization_id.hex[:8]}"),
            (other_organization_id, f"PII-AUDIT-{other_organization_id.hex[:8]}"),
        ):
            await owner.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $2, 'active', now(), now())
                """,
                tenant_id,
                code,
            )
        await owner.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'PII audit actor', 'active', now(), now())
            """,
            actor_user_id,
            f"pii-audit-{actor_user_id.hex[:8]}",
        )

        auditor = CommittedPiiRevealAuditor(runtime_session)
        await auditor.persist_committed_reveal(
            PiiRevealAuditEvent(
                organization_id=organization_id,
                application_id=application_id,
                actor_user_id=actor_user_id,
                actor_role="SHELTER_ADMIN",
                purpose_code="application_review",
                request_id=request_id,
                policy_version="volunteer-pii-v1",
                provided_fields=("applicant_name", "phone_number"),
                encryption_key_version="test-v1",
                retention_expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            )
        )

        row = await owner.fetchrow(
            """
            SELECT organization_id, actor_user_id, action, resource_id, after_data
            FROM audit_records
            WHERE organization_id = $1 AND resource_id = $2
            """,
            organization_id,
            application_id,
        )
        assert row is not None
        assert row["actor_user_id"] == actor_user_id
        assert row["action"] == "pii.revealed"
        after_data = json.loads(row["after_data"])
        assert after_data["purpose_code"] == "application_review"
        assert after_data["request_id"] == str(request_id)

        await owner.execute("BEGIN")
        await owner.execute("SET LOCAL ROLE strayhub_runtime")
        await owner.execute(
            "SELECT set_config('app.current_org_id', $1, true)",
            str(other_organization_id),
        )
        assert (
            await owner.fetchval(
                "SELECT count(*) FROM audit_records WHERE resource_id = $1",
                application_id,
            )
            == 0
        )
        await owner.execute("ROLLBACK")
    finally:
        await owner.execute(
            "DELETE FROM audit_records WHERE organization_id = $1 AND resource_id = $2",
            organization_id,
            application_id,
        )
        await owner.execute("DELETE FROM users WHERE id = $1", actor_user_id)
        await owner.execute(
            "DELETE FROM organizations WHERE id = ANY($1::uuid[])",
            [organization_id, other_organization_id],
        )
        await owner.close()
        await engine.dispose()
