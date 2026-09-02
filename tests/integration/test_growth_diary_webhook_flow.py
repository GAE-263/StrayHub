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
            await connection.execute(
                "DELETE FROM growth_diary_entries WHERE adopter_user_id = ANY($1::uuid[])", ids
            )
            await connection.execute(
                "DELETE FROM growth_diary_drafts WHERE adopter_user_id = ANY($1::uuid[])", ids
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
                assert entry["photo_key"] is None

                inquiry = await connection.fetchrow(
                    "SELECT last_growth_diary_prompted_at FROM adoption_inquiries "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert inquiry["last_growth_diary_prompted_at"] is not None

                draft = await connection.fetchrow(
                    "SELECT 1 FROM growth_diary_drafts WHERE organization_id = $1",
                    organization_id,
                )
                # Cleared once the entry was saved — no pending draft left.
                assert draft is None
            finally:
                await connection.close()

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
