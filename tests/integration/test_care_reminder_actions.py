from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.application.care_reminder_service import CareReminderService
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope

DATABASE_URL = os.getenv(
    "STRAYHUB_TEST_DATABASE_URL",
    "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
)
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _seed_occurrence() -> dict:
    await engine.dispose(close=False)
    ids = {
        name: uuid4()
        for name in (
            "org",
            "user",
            "membership",
            "animal",
            "series",
            "lineage",
            "occurrence",
        )
    }
    connection = await asyncpg.connect(DATABASE_URL)
    try:
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Action Test', $2, 'active', now(), now())
            """,
            ids["org"],
            f"ACTION-{ids['org'].hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Action User', 'active', now(), now())
            """,
            ids["user"],
            f"action-{ids['user'].hex[:10]}",
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
            VALUES ($1, $2, 'Action Animal', $3, 'active', now(), now())
            """,
            ids["animal"],
            ids["org"],
            f"ACTION-{ids['animal'].hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO care_reminder_series
                (id, lineage_id, organization_id, animal_id, reminder_type, title,
                 anchor_local_date, anchor_local_time, frequency, created_by_user_id,
                 updated_by_user_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'medication', 'Action reminder', current_date,
                    '09:00', 'none', $5, $5, now(), now())
            """,
            ids["series"],
            ids["lineage"],
            ids["org"],
            ids["animal"],
            ids["user"],
        )
        await connection.execute(
            """
            INSERT INTO care_reminder_occurrences
                (id, organization_id, lineage_id, series_id, occurrence_index,
                 nominal_local_date, nominal_local_time, original_scheduled_at, scheduled_at,
                 effective_timezone, timezone_version, title_snapshot, type_snapshot,
                 created_at, updated_at)
            VALUES ($1, $2, $3, $4, 0, current_date, '09:00', now(), now(),
                    'Asia/Taipei', 1, 'Action reminder', 'medication', now(), now())
            """,
            ids["occurrence"],
            ids["org"],
            ids["lineage"],
            ids["series"],
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
        ):
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


async def test_complete_records_actual_server_time_actor_action_and_audit() -> None:
    ids = await _seed_occurrence()
    actual = datetime.now(timezone.utc) - timedelta(minutes=10)
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            result = await CareReminderService(session, _context(ids)).act(
                ids["occurrence"],
                "completed",
                None,
                "狀況正常",
                "complete-once",
                {"actual_completed_at": actual},
                1,
            )
            assert result.occurrence.status == "completed"
            assert result.occurrence.actual_completed_at == actual
            assert result.occurrence.recorded_at >= actual
            assert result.occurrence.completed_by_user_id == ids["user"]
            assert result.action.before_state["status"] == "pending"
            assert result.action.after_state["status"] == "completed"
            assert result.action.result_note == "狀況正常"
        connection = await asyncpg.connect(DATABASE_URL)
        try:
            assert (
                await connection.fetchval(
                    """
                    SELECT count(*) FROM audit_records
                    WHERE organization_id=$1 AND action='care_reminder.completed'
                    """,
                    ids["org"],
                )
                == 1
            )
        finally:
            await connection.close()
    finally:
        await _cleanup(ids)


async def test_complete_defaults_actual_time_to_server_recorded_time() -> None:
    ids = await _seed_occurrence()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            result = await CareReminderService(session, _context(ids)).act(
                ids["occurrence"],
                "completed",
                None,
                None,
                "complete-default-time",
                expected_version=1,
            )

            assert result.occurrence.actual_completed_at == result.occurrence.recorded_at
            assert result.occurrence.recorded_at == result.action.acted_at
    finally:
        await _cleanup(ids)


@pytest.mark.parametrize("action", ["skipped", "cancelled", "rescheduled"])
async def test_non_complete_actions_preserve_reason_and_state(action: str) -> None:
    ids = await _seed_occurrence()
    try:
        connection = await asyncpg.connect(DATABASE_URL)
        try:
            original_scheduled_at = await connection.fetchval(
                "SELECT scheduled_at FROM care_reminder_occurrences WHERE id = $1",
                ids["occurrence"],
            )
        finally:
            await connection.close()
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            data = (
                {"scheduled_at": datetime.now(timezone.utc) + timedelta(days=1)}
                if action == "rescheduled"
                else None
            )
            result = await CareReminderService(session, _context(ids)).act(
                ids["occurrence"], action, "人工原因", None, f"{action}-once", data, 1
            )
            assert result.occurrence.status == ("pending" if action == "rescheduled" else action)
            assert result.action.reason == "人工原因"
            assert result.action.before_state["status"] == "pending"
            assert result.action.after_state["status"] == result.occurrence.status
            if action == "rescheduled":
                assert result.occurrence.original_scheduled_at == original_scheduled_at
                assert (
                    result.action.before_state["scheduled_at"]
                    != (result.action.after_state["scheduled_at"])
                )
    finally:
        await _cleanup(ids)
