from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.care_reminder_service import (
    CareReminderService,
    ReminderActionResult,
)
from services.api.app.domain.care_recurrence import occurrence_id
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from tests.integration.test_care_reminder_actions import (
    DATABASE_URL,
    _cleanup,
    _context,
    _seed_occurrence,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _act(ids: dict, *, key: str, note: str, expected_version: int = 1):
    async with session_factory() as session:
        await set_organization_scope(session, ids["org"])
        return await CareReminderService(session, _context(ids)).act(
            ids["occurrence"],
            "completed",
            None,
            note,
            key,
            expected_version=expected_version,
        )


async def test_same_idempotency_key_replays_original_result() -> None:
    ids = await _seed_occurrence()
    try:
        first = await _act(ids, key="same-request", note="第一次")
        replay = await _act(ids, key="same-request", note="第一次")

        assert replay.action.id == first.action.id
        assert replay.occurrence.id == first.occurrence.id
        assert replay.occurrence.version == first.occurrence.version

        connection = await asyncpg.connect(DATABASE_URL)
        try:
            assert (
                await connection.fetchval(
                    """
                    SELECT count(*) FROM care_reminder_actions
                    WHERE organization_id = $1 AND idempotency_key = 'same-request'
                    """,
                    ids["org"],
                )
                == 1
            )
        finally:
            await connection.close()
    finally:
        await _cleanup(ids)


async def test_same_idempotency_key_with_different_payload_conflicts() -> None:
    ids = await _seed_occurrence()
    try:
        await _act(ids, key="reused-request", note="原始內容")

        with pytest.raises(DomainError) as caught:
            await _act(ids, key="reused-request", note="不同內容")

        assert caught.value.status_code == 409
        assert caught.value.code == "idempotency_key_reused"
    finally:
        await _cleanup(ids)


async def test_concurrent_same_key_replays_winning_action() -> None:
    ids = await _seed_occurrence()
    try:
        results = await asyncio.gather(
            _act(ids, key="concurrent-replay", note="相同內容"),
            _act(ids, key="concurrent-replay", note="相同內容"),
        )

        assert results[0].action.id == results[1].action.id
        assert results[0].occurrence.version == results[1].occurrence.version == 2
    finally:
        await _cleanup(ids)


async def test_stale_expected_version_returns_safe_conflict() -> None:
    ids = await _seed_occurrence()
    try:
        first_due = datetime.now(timezone.utc) + timedelta(days=1)
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            first = await CareReminderService(session, _context(ids)).act(
                ids["occurrence"],
                "rescheduled",
                "延後一天",
                None,
                "reschedule-first",
                {"scheduled_at": first_due},
                1,
            )
        assert first.occurrence.scheduled_at == first_due

        with pytest.raises(DomainError) as caught:
            await _act(ids, key="stale-complete", note="舊畫面", expected_version=1)

        assert caught.value.status_code == 409
        assert caught.value.code == "occurrence_version_conflict"
        assert "重新載入" in caught.value.message
    finally:
        await _cleanup(ids)


async def test_two_workers_can_only_complete_once() -> None:
    ids = await _seed_occurrence()
    try:
        connection = await asyncpg.connect(DATABASE_URL)
        try:
            await connection.execute(
                "DELETE FROM care_reminder_occurrences WHERE organization_id = $1",
                ids["org"],
            )
        finally:
            await connection.close()
        ids["occurrence"] = occurrence_id(ids["lineage"], 0)

        results = await asyncio.gather(
            _act(ids, key="worker-a", note="A 完成"),
            _act(ids, key="worker-b", note="B 完成"),
            return_exceptions=True,
        )

        successes = [item for item in results if isinstance(item, ReminderActionResult)]
        conflicts = [item for item in results if isinstance(item, DomainError)]
        assert len(successes) == 1
        assert len(conflicts) == 1
        assert conflicts[0].status_code == 409
        assert conflicts[0].code == "occurrence_version_conflict"

        connection = await asyncpg.connect(DATABASE_URL)
        try:
            assert (
                await connection.fetchval(
                    """
                    SELECT count(*) FROM care_reminder_actions
                    WHERE organization_id = $1 AND action_type = 'completed'
                    """,
                    ids["org"],
                )
                == 1
            )
        finally:
            await connection.close()
    finally:
        await _cleanup(ids)
