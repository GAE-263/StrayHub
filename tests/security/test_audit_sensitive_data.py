from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.database.engine import engine
from services.api.app.persistence.models.audit import AuditRecord
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


class _Session:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def add(self, record: AuditRecord) -> None:
        self.records.append(record)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_audit_service_preventively_redacts_nested_secrets_without_mutating_caller() -> None:
    sentinel_values = (
        "before-password-sentinel",
        "after-token-sentinel",
        "nested-entry-sentinel",
        "reason-authorization-sentinel",
    )
    before = {
        "status": "pending",
        "Password": sentinel_values[0],
        "nested": [{"url": f"/volunteer-entry?entry={sentinel_values[2]}&page=2"}],
    }
    after = {
        "status": "approved",
        "headers": {"authorization": f"Bearer {sentinel_values[1]}"},
        "links": [f"https://example.test/photo?token={sentinel_values[1]}&v=4"],
    }
    original_before = deepcopy(before)
    original_after = deepcopy(after)
    session = _Session()

    record = await AuditService(session).record(
        organization_id=uuid4(),
        actor_user_id=uuid4(),
        action="volunteer.reviewed",
        resource_type="volunteer_application",
        resource_id=uuid4(),
        source_channel="api",
        before=before,
        after=after,
        reason=f"Authorization: Bearer {sentinel_values[3]}",
        result="success",
    )

    assert before == original_before
    assert after == original_after
    rendered = repr((record.before_data, record.after_data, record.reason))
    assert all(value not in rendered for value in sentinel_values)
    assert record.before_data["status"] == "pending"
    assert record.after_data["status"] == "approved"
    assert "page=2" in rendered
    assert "v=4" in rendered
    assert record.action == "volunteer.reviewed"
    assert record.result == "success"


@pytest.mark.asyncio
async def test_database_persisted_audit_json_contains_no_raw_secret() -> None:
    organization_id = uuid4()
    actor_id = uuid4()
    audit_id = None
    sentinel = "database-audit-secret-sentinel"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO organizations (id, name, code, status, created_at, updated_at) "
                "VALUES (:id, 'Audit Security', :code, 'active', now(), now())"
            ),
            {"id": organization_id, "code": f"AUD-{organization_id.hex[:8]}"},
        )
        await connection.execute(
            text(
                "INSERT INTO users (id, username, display_name, status, created_at, updated_at) "
                "VALUES (:id, :username, 'Audit Actor', 'active', now(), now())"
            ),
            {"id": actor_id, "username": f"audit-{actor_id.hex}"},
        )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            record = await AuditService(session).record(
                organization_id=organization_id,
                actor_user_id=actor_id,
                action="security.preventive_test",
                resource_type="volunteer_application",
                source_channel="test",
                before={"safe_fingerprint": "sha256:abc", "refresh_token": sentinel},
                after={"nested": {"url": f"/callback?access_token={sentinel}"}},
                reason=f"password={sentinel}",
            )
            audit_id = record.id
            await session.commit()

        async with AsyncSession(engine) as session:
            persisted = await session.scalar(select(AuditRecord).where(AuditRecord.id == audit_id))
            assert persisted is not None
            rendered = repr((persisted.before_data, persisted.after_data, persisted.reason))
            assert sentinel not in rendered
            assert persisted.before_data["safe_fingerprint"] == "sha256:abc"
    finally:
        async with engine.begin() as connection:
            if audit_id is not None:
                await connection.execute(
                    text("DELETE FROM audit_records WHERE id = :id"), {"id": audit_id}
                )
            await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": actor_id})
            await connection.execute(
                text("DELETE FROM organizations WHERE id = :id"), {"id": organization_id}
            )
