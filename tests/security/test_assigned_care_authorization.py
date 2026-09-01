from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.animal_timeline import animal_timeline
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.application.assigned_care_service import AssignedCareService
from services.api.app.domain.medical_care_access import permission_for, require_medical_view
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope

DATABASE_URL = os.getenv(
    "STRAYHUB_TEST_DATABASE_URL",
    "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
)
pytestmark = pytest.mark.asyncio


async def _seed_assigned_care() -> dict:
    await engine.dispose(close=False)
    names = (
        "org_a",
        "org_b",
        "user",
        "other_user",
        "membership",
        "other_membership",
        "animal_a",
        "animal_b",
        "series_a",
        "series_b",
        "lineage_a",
        "lineage_b",
        "occurrence_a",
        "occurrence_b",
    )
    ids = {name: uuid4() for name in names}
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        for org_key in ("org_a", "org_b"):
            await connection.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', now(), now())
                """,
                ids[org_key],
                f"Assigned {org_key}",
                f"ASSIGNED-{ids[org_key].hex[:10]}",
            )
        for user_key in ("user", "other_user"):
            await connection.execute(
                """
                INSERT INTO users (id, username, display_name, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', now(), now())
                """,
                ids[user_key],
                f"assigned-{ids[user_key].hex[:10]}",
                f"Assigned {user_key}",
            )
        valid_from = datetime.now(timezone.utc) - timedelta(days=1)
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, medical_care_access,
                 valid_from, expires_at, created_at, updated_at)
            VALUES ($1, $2, $3, 'VOLUNTEER', 'active', false, $4, $5, now(), now())
            """,
            ids["membership"],
            ids["org_a"],
            ids["user"],
            valid_from,
            expires_at,
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, medical_care_access,
                 valid_from, expires_at, created_at, updated_at)
            VALUES ($1, $2, $3, 'VOLUNTEER', 'active', false, $4, $5, now(), now())
            """,
            ids["other_membership"],
            ids["org_a"],
            ids["other_user"],
            valid_from,
            expires_at,
        )
        for suffix in ("a", "b"):
            await connection.execute(
                """
                INSERT INTO animals
                    (id, organization_id, name, shelter_number, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, 'active', now(), now())
                """,
                ids[f"animal_{suffix}"],
                ids[f"org_{suffix}"],
                f"Assigned animal {suffix}",
                f"ASSIGNED-{suffix.upper()}",
            )
            await connection.execute(
                """
                INSERT INTO care_reminder_series
                    (id, lineage_id, organization_id, animal_id, reminder_type, title,
                     instructions, assignee_membership_id, anchor_local_date,
                     anchor_local_time, frequency, created_by_user_id, updated_by_user_id,
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, 'medication', $5, '依照獸醫指示執行', $6,
                        current_date, '09:00', 'none', $7, $7, now(), now())
                """,
                ids[f"series_{suffix}"],
                ids[f"lineage_{suffix}"],
                ids[f"org_{suffix}"],
                ids[f"animal_{suffix}"],
                f"Assigned reminder {suffix}",
                ids["membership"] if suffix == "a" else None,
                ids["user"],
            )
            await connection.execute(
                """
                INSERT INTO care_reminder_occurrences
                    (id, organization_id, lineage_id, series_id, occurrence_index,
                     nominal_local_date, nominal_local_time, original_scheduled_at,
                     scheduled_at, effective_timezone, timezone_version, status,
                     assignee_membership_id, title_snapshot, instructions_snapshot,
                     type_snapshot, created_at, updated_at)
                VALUES ($1, $2, $3, $4, 0, current_date, '09:00', now(), now(),
                        'Asia/Taipei', 1, 'pending', $5, $6, '依照獸醫指示執行',
                        'medication', now(), now())
                """,
                ids[f"occurrence_{suffix}"],
                ids[f"org_{suffix}"],
                ids[f"lineage_{suffix}"],
                ids[f"series_{suffix}"],
                ids["membership"] if suffix == "a" else None,
                f"Assigned reminder {suffix}",
            )
    finally:
        await connection.close()
        await engine.dispose(close=False)
    return ids


async def _cleanup(ids: dict) -> None:
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        for table in (
            "audit_records",
            "care_reminder_actions",
            "care_reminder_occurrences",
            "care_reminder_series",
            "animals",
            "organization_memberships",
        ):
            await connection.execute(
                f"DELETE FROM {table} WHERE organization_id = ANY($1::uuid[])",
                [ids["org_a"], ids["org_b"]],
            )
        await connection.execute(
            "DELETE FROM users WHERE id = ANY($1::uuid[])",
            [ids["user"], ids["other_user"]],
        )
        await connection.execute(
            "DELETE FROM organizations WHERE id = ANY($1::uuid[])",
            [ids["org_a"], ids["org_b"]],
        )
    finally:
        await connection.close()
        await engine.dispose(close=False)


def _context(ids: dict) -> RequestContext:
    return RequestContext(
        user_id=ids["user"],
        organization_id=ids["org_a"],
        membership_id=ids["membership"],
        role="VOLUNTEER",
    )


async def test_assigned_projection_contains_only_minimum_fields() -> None:
    ids = await _seed_assigned_care()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org_a"])
            item = await AssignedCareService(session, _context(ids)).get(ids["occurrence_a"])

        payload = asdict(item)
        assert set(payload) == {
            "occurrence_id",
            "version",
            "status",
            "animal",
            "reminder_type",
            "title",
            "instructions",
            "display_local_at",
            "can_complete",
            "can_skip",
        }
        assert set(payload["animal"]) == {"id", "name", "shelter_number", "photo_url"}
        forbidden = {
            "organization_id",
            "series_id",
            "lineage_id",
            "clinic",
            "veterinarian",
            "weight_kg",
            "attachments",
            "medical_records",
            "assignee_membership_id",
        }
        assert forbidden.isdisjoint(payload)
    finally:
        await _cleanup(ids)


@pytest.mark.parametrize("action", ["completed", "skipped"])
async def test_assigned_volunteer_can_complete_or_skip(action: str) -> None:
    ids = await _seed_assigned_care()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org_a"])
            result = await AssignedCareService(session, _context(ids)).act(
                ids["occurrence_a"],
                action=action,
                expected_version=1,
                reason="現場無法執行" if action == "skipped" else None,
                result_note="已確認" if action == "completed" else None,
                actual_completed_at=None,
                idempotency_key=f"assigned-{action}",
            )

        assert result.occurrence.status == action
        if action == "completed":
            assert result.actual_completed_at == result.recorded_at
    finally:
        await _cleanup(ids)


async def test_unassigned_revoked_and_cross_tenant_resources_are_hidden() -> None:
    ids = await _seed_assigned_care()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org_a"])
            service = AssignedCareService(session, _context(ids))
            with pytest.raises(DomainError) as cross_tenant:
                await service.get(ids["occurrence_b"])
            assert cross_tenant.value.status_code == 404

        connection = await asyncpg.connect(DATABASE_URL)
        try:
            await connection.execute(
                """
                UPDATE care_reminder_series SET assignee_membership_id = $1
                WHERE id = $2
                """,
                ids["other_membership"],
                ids["series_a"],
            )
        finally:
            await connection.close()
        async with session_factory() as session:
            await set_organization_scope(session, ids["org_a"])
            with pytest.raises(DomainError) as unassigned:
                await AssignedCareService(session, _context(ids)).get(ids["occurrence_a"])
            assert unassigned.value.status_code == 404

        connection = await asyncpg.connect(DATABASE_URL)
        try:
            await connection.execute(
                "UPDATE organization_memberships SET status = 'inactive' WHERE id = $1",
                ids["membership"],
            )
        finally:
            await connection.close()
        async with session_factory() as session:
            await set_organization_scope(session, ids["org_a"])
            with pytest.raises(DomainError) as revoked:
                await AssignedCareService(session, _context(ids)).list()
            assert revoked.value.status_code == 404
    finally:
        await _cleanup(ids)


async def test_volunteer_cannot_use_full_timeline_endpoint() -> None:
    ids = await _seed_assigned_care()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org_a"])
            with pytest.raises(DomainError) as denied:
                await animal_timeline(
                    ids["animal_a"],
                    start_date=None,
                    end_date=None,
                    _context=_context(ids),
                    session=session,
                )
        assert denied.value.status_code == 403
        assert denied.value.code == "timeline_access_denied"
    finally:
        await _cleanup(ids)


async def test_volunteer_cannot_use_full_medical_permission() -> None:
    permission = permission_for(role="VOLUNTEER", membership_active=True, medical_care_access=True)
    with pytest.raises(DomainError) as denied:
        require_medical_view(permission)
    assert denied.value.status_code == 403
