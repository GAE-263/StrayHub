from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.persistence.database.engine import engine, session_factory
from services.worker.app.handlers.growth_diary_reminder_handler import (
    GrowthDiaryReminderHandler,
)


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


class _FakeMessaging:
    def __init__(self) -> None:
        self.pushes: list[tuple[str, list[dict]]] = []

    async def push(self, *, to_user_id: str, messages: list[dict]) -> None:
        self.pushes.append((to_user_id, messages))


async def _insert_inquiry(
    *,
    organization_id,
    adopter_user_id,
    animal_id,
    line_user_id: str | None,
    submitted_at: datetime,
    last_growth_diary_prompted_at: datetime | None,
) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Reminder Handler Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"REMIND-{organization_id.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Reminder Handler Adopter', 'active', now(), now())
            """,
            adopter_user_id,
            f"reminder-adopter-{adopter_user_id.hex[:10]}",
        )
        if line_user_id is not None:
            await connection.execute(
                """
                INSERT INTO line_user_bindings
                    (id, line_user_id, user_id, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', now(), now())
                """,
                uuid4(),
                line_user_id,
                adopter_user_id,
            )
        draft_id = uuid4()
        inquiry_id = uuid4()
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, status, is_adoptable, created_at, updated_at)
            VALUES ($1, $2, '旺來', 'active', true, now(), now())
            """,
            animal_id,
            organization_id,
        )
        await connection.execute(
            """
            INSERT INTO adoption_drafts
                (id, opaque_token_digest, organization_id, adopter_user_id, path,
                 target_animal_id, current_step, status, last_interaction_at,
                 expires_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'specific_animal', $5, 'submitted', 'submitted',
                    now(), now() + interval '1 day', now(), now())
            """,
            draft_id,
            draft_id.hex,
            organization_id,
            adopter_user_id,
            animal_id,
        )
        await connection.execute(
            """
            INSERT INTO adoption_inquiries
                (id, organization_id, draft_id, adopter_user_id, path, target_animal_id,
                 animal_name_snapshot, answers, phone_number, status, submitted_at,
                 last_growth_diary_prompted_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'specific_animal', $5, '旺來', '{}'::jsonb, '0912345678',
                    'closed', $6, $7, now(), now())
            """,
            inquiry_id,
            organization_id,
            draft_id,
            adopter_user_id,
            animal_id,
            submitted_at,
            last_growth_diary_prompted_at,
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


async def _cleanup(*, organization_id, adopter_user_id, line_user_id: str | None) -> None:
    cleanup = await asyncpg.connect(_database_url())
    try:
        await cleanup.execute("BEGIN")
        await cleanup.execute(
            "DELETE FROM adoption_inquiries WHERE organization_id = $1", organization_id
        )
        await cleanup.execute(
            "DELETE FROM adoption_drafts WHERE organization_id = $1", organization_id
        )
        await cleanup.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        if line_user_id is not None:
            await cleanup.execute(
                "DELETE FROM line_user_bindings WHERE line_user_id = $1", line_user_id
            )
        await cleanup.execute("DELETE FROM users WHERE id = $1", adopter_user_id)
        await cleanup.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await cleanup.execute("COMMIT")
    finally:
        await cleanup.close()


@pytest.mark.asyncio
async def test_send_due_reminders_pushes_card_and_advances_clock() -> None:
    await engine.dispose(close=False)
    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    line_user_id = f"Uremind{uuid4().hex}"
    now = datetime.now(timezone.utc)
    await _insert_inquiry(
        organization_id=organization_id,
        adopter_user_id=adopter_user_id,
        animal_id=animal_id,
        line_user_id=line_user_id,
        submitted_at=now - timedelta(days=10),  # early phase, no prompt yet -> due
        last_growth_diary_prompted_at=None,
    )
    try:
        messaging = _FakeMessaging()
        async with session_factory() as session:
            async with session.begin():
                sent = await GrowthDiaryReminderHandler(session).send_due_reminders(
                    organization_id, messaging=messaging, now=now
                )
        assert sent == 1
        assert len(messaging.pushes) == 1
        to_user_id, messages = messaging.pushes[0]
        assert to_user_id == line_user_id
        assert "旺來" in str(messages)

        async def _verify_clock_advanced() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                inquiry = await connection.fetchrow(
                    "SELECT last_growth_diary_prompted_at FROM adoption_inquiries "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert inquiry["last_growth_diary_prompted_at"] is not None
            finally:
                await connection.close()

        await _verify_clock_advanced()
    finally:
        await _cleanup(
            organization_id=organization_id,
            adopter_user_id=adopter_user_id,
            line_user_id=line_user_id,
        )


@pytest.mark.asyncio
async def test_send_due_reminders_skips_when_not_due_yet() -> None:
    await engine.dispose(close=False)
    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    line_user_id = f"Uremind{uuid4().hex}"
    now = datetime.now(timezone.utc)
    await _insert_inquiry(
        organization_id=organization_id,
        adopter_user_id=adopter_user_id,
        animal_id=animal_id,
        line_user_id=line_user_id,
        submitted_at=now - timedelta(days=10),
        last_growth_diary_prompted_at=now - timedelta(days=2),  # < 7-day early cadence
    )
    try:
        messaging = _FakeMessaging()
        async with session_factory() as session:
            async with session.begin():
                sent = await GrowthDiaryReminderHandler(session).send_due_reminders(
                    organization_id, messaging=messaging, now=now
                )
        assert sent == 0
        assert messaging.pushes == []
    finally:
        await _cleanup(
            organization_id=organization_id,
            adopter_user_id=adopter_user_id,
            line_user_id=line_user_id,
        )


@pytest.mark.asyncio
async def test_send_due_reminders_advances_clock_without_pushing_when_unbound() -> None:
    """No LINE binding to push to — the clock still advances so this
    inquiry isn't re-evaluated as "due" on every single worker iteration."""
    await engine.dispose(close=False)
    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    await _insert_inquiry(
        organization_id=organization_id,
        adopter_user_id=adopter_user_id,
        animal_id=animal_id,
        line_user_id=None,
        submitted_at=now - timedelta(days=10),
        last_growth_diary_prompted_at=None,
    )
    try:
        messaging = _FakeMessaging()
        async with session_factory() as session:
            async with session.begin():
                sent = await GrowthDiaryReminderHandler(session).send_due_reminders(
                    organization_id, messaging=messaging, now=now
                )
        assert sent == 0
        assert messaging.pushes == []

        async def _verify_clock_advanced_anyway() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                inquiry = await connection.fetchrow(
                    "SELECT last_growth_diary_prompted_at FROM adoption_inquiries "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert inquiry["last_growth_diary_prompted_at"] is not None
            finally:
                await connection.close()

        await _verify_clock_advanced_anyway()
    finally:
        await _cleanup(
            organization_id=organization_id, adopter_user_id=adopter_user_id, line_user_id=None
        )


@pytest.mark.asyncio
async def test_send_due_reminders_uses_monthly_cadence_after_three_months() -> None:
    await engine.dispose(close=False)
    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    line_user_id = f"Uremind{uuid4().hex}"
    now = datetime.now(timezone.utc)
    await _insert_inquiry(
        organization_id=organization_id,
        adopter_user_id=adopter_user_id,
        animal_id=animal_id,
        line_user_id=line_user_id,
        submitted_at=now - timedelta(days=120),
        last_growth_diary_prompted_at=now - timedelta(days=10),  # < 30-day stable cadence
    )
    try:
        messaging = _FakeMessaging()
        async with session_factory() as session:
            async with session.begin():
                sent = await GrowthDiaryReminderHandler(session).send_due_reminders(
                    organization_id, messaging=messaging, now=now
                )
        assert sent == 0
    finally:
        await _cleanup(
            organization_id=organization_id,
            adopter_user_id=adopter_user_id,
            line_user_id=line_user_id,
        )
