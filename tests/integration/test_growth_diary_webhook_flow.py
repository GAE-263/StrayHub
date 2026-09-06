from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
from uuid import UUID, uuid4

import asyncpg
from fastapi.testclient import TestClient
from services.api.app.config.settings import get_settings
from services.api.app.main import app
from services.api.app.persistence.database.engine import engine


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test",
    )


def _event(line_user_id: str, data: str) -> dict:
    return {
        "type": "postback",
        "webhookEventId": uuid4().hex,
        "source": {"userId": line_user_id},
        "postback": {"data": data},
    }


def _text_event(line_user_id: str, text: str) -> dict:
    return {
        "type": "message",
        "webhookEventId": uuid4().hex,
        "source": {"userId": line_user_id},
        "message": {"type": "text", "id": uuid4().hex, "text": text},
    }


def _post(client: TestClient, events: list[dict]):
    asyncio.run(engine.dispose(close=False))
    body = json.dumps({"events": events}).encode()
    secret = get_settings().line_channel_secret
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return client.post(
        "/v1/line/webhook",
        content=body,
        headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
    )


async def _seed(organization_id: UUID, animal_id: UUID) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, region, status, created_at, updated_at)
            VALUES ($1, 'Growth Diary Shelter', $2, 'north', 'active', now(), now())
            """,
            organization_id,
            f"DIARY-{organization_id.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, is_adoptable,
                 size, energy, temperament, created_at, updated_at)
            VALUES ($1, $2, '旺來', 'A200', 'active', true,
                    'medium', 'medium', '[]'::jsonb, now(), now())
            """,
            animal_id,
            organization_id,
        )
    finally:
        await connection.close()


async def _cleanup(organization_id: UUID, line_user_ids: tuple[str, ...]) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        user_ids = await connection.fetch(
            "SELECT user_id FROM line_user_bindings WHERE line_user_id = ANY($1::text[])",
            list(line_user_ids),
        )
        await connection.execute(
            "DELETE FROM audit_records WHERE organization_id = $1", organization_id
        )
        if user_ids:
            ids = [row["user_id"] for row in user_ids]
            # Drafts before entries — a draft's current_entry_id now stays
            # pointed at its day's entry instead of being cleared once saved
            # (see the daily-thread redesign), so deleting entries first
            # would violate that foreign key.
            await connection.execute(
                "DELETE FROM growth_diary_drafts WHERE adopter_user_id = ANY($1::uuid[])", ids
            )
            await connection.execute(
                "DELETE FROM growth_diary_entries WHERE adopter_user_id = ANY($1::uuid[])", ids
            )
        await connection.execute(
            "DELETE FROM adoption_inquiries WHERE organization_id = $1", organization_id
        )
        if user_ids:
            ids = [row["user_id"] for row in user_ids]
            await connection.execute(
                "DELETE FROM adoption_drafts WHERE adopter_user_id = ANY($1::uuid[])", ids
            )
            await connection.execute(
                "DELETE FROM line_user_bindings WHERE user_id = ANY($1::uuid[])", ids
            )
            await connection.execute("DELETE FROM users WHERE id = ANY($1::uuid[])", ids)
        await connection.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        await connection.execute("DELETE FROM organizations WHERE id = $1", organization_id)
    finally:
        await connection.close()


def _submit_adoption_inquiry(
    client: TestClient, line_user_id: str, organization_id, animal_id
) -> None:
    """Drives the full 心有所屬 flow to a submitted inquiry — this is what
    naturally creates the LineUserBinding and AdoptionInquiry growth diary
    needs; there is no shortcut fixture for those on this branch."""
    actions = [
        "action=start_adoption_matching&flow=adoption",
        f"action=select_organization&flow=adoption&value={organization_id}",
        "action=choose_path&flow=adoption&value=specific_animal",
        f"action=select_target_animal&flow=adoption&value={animal_id}",
        "action=confirm_target_animal&flow=adoption",
        # Skip the free-text self-introduction step (方向 D) and fall back
        # to the one-by-one questions below — same escape hatch a real
        # adopter gets from the "還是想一題一題回答" quick reply.
        "action=finish_freetext_profile&flow=adoption",
    ]
    actions.extend(
        f"action=answer&flow=adoption&value={value}"
        for value in (
            "apartment_small",
            "first_time",
            "none",
            "adults_only",
            "work_from_home",
            "structured",
            "high_patience",
            "companionship",
        )
    )
    actions.append("action=confirm_answers&flow=adoption")
    for action in actions:
        result = _post(client, [_event(line_user_id, action)]).json()["event_results"][0]
        assert result["status"] == "processed", result
    for value in ("王小明", "平日白天", "0911222333"):
        result = _post(client, [_text_event(line_user_id, value)]).json()["event_results"][0]
        assert result["status"] == "processed", result
    result = _post(client, [_event(line_user_id, "action=submit&flow=adoption")]).json()[
        "event_results"
    ][0]
    assert result["status"] == "processed", result


def test_growth_diary_command_without_any_inquiry_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-webhook")
    get_settings.cache_clear()
    line_user_id = f"Udiary{uuid4().hex}"
    try:
        client = TestClient(app)
        result = _post(client, [_text_event(line_user_id, "毛孩日記")]).json()["event_results"][0]
        # No LINE binding exists at all yet — rejected before touching any
        # growth-diary table.
        assert result["status"] == "processed", result
    finally:
        get_settings.cache_clear()


def test_growth_diary_entry_records_note_and_resets_reminder_clock(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)

        result = _post(client, [_text_event(line_user_id, "毛孩日記")]).json()["event_results"][0]
        assert result["status"] == "processed", result

        result = _post(
            client, [_event(line_user_id, "action=start_growth_diary_entry&flow=growth_diary")]
        ).json()["event_results"][0]
        assert result["status"] == "processed", result

        result = _post(client, [_text_event(line_user_id, "今天精神很好，吃了兩碗飯！")]).json()[
            "event_results"
        ][0]
        assert result["status"] == "processed", result

        async def verify() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                entry = await connection.fetchrow(
                    "SELECT * FROM growth_diary_entries WHERE organization_id = $1",
                    organization_id,
                )
                assert entry is not None
                assert entry["note"] == "今天精神很好，吃了兩碗飯！"
                assert json.loads(entry["photo_keys"]) == []

                inquiry = await connection.fetchrow(
                    "SELECT last_growth_diary_prompted_at FROM adoption_inquiries "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert inquiry["last_growth_diary_prompted_at"] is not None

                draft = await connection.fetchrow(
                    "SELECT current_entry_id, entry_date FROM growth_diary_drafts "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                # No longer cleared once the entry is saved — it now stays
                # around as "today's open thread" so a same-day follow-up
                # message merges onto this same entry (see
                # _handle_growth_diary_message / append_to_entry).
                assert draft is not None
                assert draft["current_entry_id"] == entry["id"]
                assert draft["entry_date"] is not None
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_same_day_messages_merge_onto_one_entry_without_retriggering(monkeypatch) -> None:
    """The point of the daily-thread redesign: once a thread is open, the
    adopter can keep sending messages the same calendar day without tapping
    "新增一篇"/"毛孩日記" again — each one merges onto the SAME entry (note
    appended, photo added to photo_keys) rather than needing a fresh
    trigger, and rather than getting the "不太確定這句話的意思" fallback."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)

        _post(client, [_text_event(line_user_id, "毛孩日記")])
        _post(client, [_event(line_user_id, "action=start_growth_diary_entry&flow=growth_diary")])
        first = _post(client, [_text_event(line_user_id, "早上吃了一碗飯")]).json()[
            "event_results"
        ][0]
        assert first["status"] == "processed", first

        # No re-trigger here — straight to another plain text message, the
        # same way a real follow-up would arrive later the same day.
        second = _post(client, [_text_event(line_user_id, "下午出去散步一小時")]).json()[
            "event_results"
        ][0]
        assert second["status"] == "processed", second

        async def verify() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                entries = await connection.fetch(
                    "SELECT note FROM growth_diary_entries WHERE organization_id = $1",
                    organization_id,
                )
                # Still exactly one entry — the second message merged onto
                # the first rather than forking a second row.
                assert len(entries) == 1
                assert entries[0]["note"] == "早上吃了一碗飯\n\n下午出去散步一小時"
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_is_adopter_only_line_user_distinguishes_bound_adopters_from_unbound_and_staff(
    monkeypatch,
) -> None:
    """Regression test for _is_adopter_only_line_user: a stray text message
    from an adopter (e.g. right after a growth-diary entry clears its
    pending draft — see test_growth_diary_entry_records_note_and_resets_
    reminder_clock) used to fall through to the staff-only _resolve_context
    path and get the confusing "請先開啟 LIFF 完成身分綁定" reply, even though
    the adopter is already bound — just not as staff. This checks the
    predicate the fix (_adopter_lost_message) is gated on: True only for a
    LINE user who IS bound but holds no organization membership anywhere;
    False for a genuinely unbound LINE user."""
    from services.api.app.api.line_webhook import _is_adopter_only_line_user
    from services.api.app.persistence.database.engine import engine, session_factory

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    unbound_line_user_id = f"Udiary{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)

        async def verify() -> None:
            # Dispose pooled connections from the TestClient's event loop
            # first — session_factory's engine can't reuse them under the
            # fresh loop asyncio.run() spins up here (see _post's identical
            # dispose call for the same reason).
            await engine.dispose(close=False)
            async with session_factory() as session:
                assert await _is_adopter_only_line_user(session, line_user_id) is True
                assert await _is_adopter_only_line_user(session, unbound_line_user_id) is False

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_growth_diary_entry_can_be_cancelled_mid_flow(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)

        _post(client, [_text_event(line_user_id, "毛孩日記")])
        _post(client, [_event(line_user_id, "action=start_growth_diary_entry&flow=growth_diary")])
        result = _post(client, [_text_event(line_user_id, "取消")]).json()["event_results"][0]
        assert result["status"] == "processed", result

        async def verify() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT 1 FROM growth_diary_drafts WHERE organization_id = $1",
                    organization_id,
                )
                assert draft is None
                entry = await connection.fetchrow(
                    "SELECT 1 FROM growth_diary_entries WHERE organization_id = $1",
                    organization_id,
                )
                assert entry is None
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_growth_diary_history_review_lists_past_entries(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-growth-diary-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        _submit_adoption_inquiry(client, line_user_id, organization_id, animal_id)

        # No entries yet — history should say so, not error.
        result = _post(
            client, [_event(line_user_id, "action=view_growth_diary_history&flow=growth_diary")]
        ).json()["event_results"][0]
        assert result["status"] == "processed", result

        _post(client, [_text_event(line_user_id, "毛孩日記")])
        _post(client, [_event(line_user_id, "action=start_growth_diary_entry&flow=growth_diary")])
        _post(client, [_text_event(line_user_id, "第一篇日記")])

        result = _post(
            client, [_event(line_user_id, "action=view_growth_diary_history&flow=growth_diary")]
        ).json()["event_results"][0]
        assert result["status"] == "processed", result
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()
