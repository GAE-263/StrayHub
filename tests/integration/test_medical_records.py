from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.medical_records import (
    MedicalRecordArchiveRequest,
    MedicalRecordCreateRequest,
    MedicalRecordUpdateRequest,
    archive_medical_record,
    create_medical_record,
    get_medical_record,
    list_medical_records,
    update_medical_record,
)
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.medical_care import MedicalRecordType

DATABASE_URL = os.getenv(
    "STRAYHUB_TEST_DATABASE_URL",
    "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
)
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_records() -> dict:
    await engine.dispose(close=False)
    ids = {name: uuid4() for name in ("org", "user", "membership", "animal")}
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        await connection.execute(
            """
            INSERT INTO organizations
                (id, name, code, status, timezone, timezone_version, created_at, updated_at)
            VALUES ($1, 'Medical Records Test', $2, 'active', 'Asia/Taipei', 1, now(), now())
            """,
            ids["org"],
            f"MEDICAL-{ids['org'].hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Medical Records User', 'active', now(), now())
            """,
            ids["user"],
            f"medical-{ids['user'].hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, medical_care_access,
                 created_at, updated_at)
            VALUES ($1, $2, $3, 'STAFF', 'active', true, now(), now())
            """,
            ids["membership"],
            ids["org"],
            ids["user"],
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, created_at, updated_at)
            VALUES ($1, $2, '醫療測試犬', $3, 'active', now(), now())
            """,
            ids["animal"],
            ids["org"],
            f"MEDICAL-{ids['animal'].hex[:8]}",
        )
    finally:
        await connection.close()
        await engine.dispose(close=False)
    return ids


async def _cleanup(ids: dict) -> None:
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        for table in ("medical_record_media", "medical_records", "audit_records"):
            await connection.execute(f"DELETE FROM {table} WHERE organization_id = $1", ids["org"])
        await connection.execute("DELETE FROM animals WHERE organization_id = $1", ids["org"])
        await connection.execute(
            "DELETE FROM organization_memberships WHERE organization_id = $1", ids["org"]
        )
        await connection.execute("DELETE FROM users WHERE id = $1", ids["user"])
        await connection.execute("DELETE FROM organizations WHERE id = $1", ids["org"])
    finally:
        await connection.close()
        await engine.dispose(close=False)


def _context(ids: dict) -> RequestContext:
    return RequestContext(
        user_id=ids["user"],
        organization_id=ids["org"],
        membership_id=ids["membership"],
        role="STAFF",
    )


def _create_payload(title: str, content: str) -> MedicalRecordCreateRequest:
    return MedicalRecordCreateRequest(
        occurred_at=datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc),
        record_type=MedicalRecordType.VISIT,
        title=title,
        content=content,
        clinic="森之心動物醫院",
        veterinarian="王醫師",
        weight_kg=Decimal("12.500"),
    )


async def test_same_day_search_update_archive_and_audit_are_preserved() -> None:
    ids = await _seed_records()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            context = _context(ids)
            first = await create_medical_record(
                ids["animal"], _create_payload("回診", "完成皮膚檢查"), context, session
            )
            second = await create_medical_record(
                ids["animal"], _create_payload("用藥", "人工記錄預防藥"), context, session
            )
            assert first.id != second.id

            page = await list_medical_records(
                ids["animal"],
                occurred_from=date(2026, 8, 16),
                occurred_to=date(2026, 8, 16),
                record_type=None,
                search="皮膚",
                include_archived=False,
                context=context,
                session=session,
            )
            assert [item.id for item in page.items] == [first.id]

            updated = await update_medical_record(
                first.id,
                MedicalRecordUpdateRequest(
                    expected_version=1,
                    title="回診（已更正）",
                    content="完成皮膚與耳朵檢查",
                    reason="補充醫師說明",
                ),
                context,
                session,
            )
            assert updated.version == 2
            assert updated.content == "完成皮膚與耳朵檢查"

            with pytest.raises(DomainError) as stale:
                await update_medical_record(
                    first.id,
                    MedicalRecordUpdateRequest(
                        expected_version=1,
                        content="不應覆蓋",
                        reason="過期畫面",
                    ),
                    context,
                    session,
                )
            assert stale.value.status_code == 409

            archived = await archive_medical_record(
                first.id,
                MedicalRecordArchiveRequest(expected_version=2, reason="重複紀錄"),
                context,
                session,
            )
            assert archived.status == "archived"

            active_page = await list_medical_records(
                ids["animal"],
                occurred_from=None,
                occurred_to=None,
                record_type=None,
                search=None,
                include_archived=False,
                context=context,
                session=session,
            )
            assert [item.id for item in active_page.items] == [second.id]
            all_page = await list_medical_records(
                ids["animal"],
                occurred_from=None,
                occurred_to=None,
                record_type=None,
                search=None,
                include_archived=True,
                context=context,
                session=session,
            )
            assert {item.id for item in all_page.items} == {first.id, second.id}

            fetched = await get_medical_record(first.id, context, session)
            assert fetched.status == "archived"
            assert fetched.archive_reason == "重複紀錄"

        connection = await asyncpg.connect(DATABASE_URL)
        try:
            actions = await connection.fetch(
                """
                SELECT action, before_data, after_data, reason
                FROM audit_records
                WHERE organization_id = $1 AND resource_type = 'MedicalRecord'
                ORDER BY created_at
                """,
                ids["org"],
            )
            assert [row["action"] for row in actions] == [
                "medical_record.created",
                "medical_record.created",
                "correction",
                "archive",
            ]
            assert actions[2]["before_data"] and actions[2]["after_data"]
            assert actions[2]["reason"] == "補充醫師說明"
        finally:
            await connection.close()
    finally:
        await _cleanup(ids)
