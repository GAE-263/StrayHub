from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg
from fastapi.testclient import TestClient
from services.api.app.config.settings import get_settings
from services.api.app.main import app
from services.api.app.persistence.database.engine import engine


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


def _signed_post(client: TestClient, events: list[dict]):
    asyncio.run(engine.dispose(close=False))
    body = json.dumps({"events": events}).encode("utf-8")
    secret = get_settings().line_channel_secret
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return client.post(
        "/v1/line/webhook",
        content=body,
        headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
    )


def _event(line_user_id: str, *, data: str | None = None, text: str | None = None) -> dict:
    base = {
        "webhookEventId": uuid4().hex,
        "source": {"userId": line_user_id},
        "replyToken": uuid4().hex,
    }
    if data is not None:
        return {**base, "type": "postback", "postback": {"data": data}}
    return {
        **base,
        "type": "message",
        "message": {"type": "text", "id": uuid4().hex, "text": text or ""},
    }


async def _insert_adopter_with_inquiries(
    *, organization_id, adopter_user_id, line_user_id, animal_specs
) -> list:
    """`animal_specs` is a list of (animal_id, name) pairs; one AdoptionInquiry
    is created per entry, all completed through this system already."""
    connection = await asyncpg.connect(_database_url())
    inquiry_ids = []
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Growth Diary Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"GROWTHDIARY-{organization_id.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Growth Diary Adopter', 'active', now(), now())
            """,
            adopter_user_id,
            f"growth-diary-adopter-{adopter_user_id.hex[:10]}",
        )
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
        for animal_id, name in animal_specs:
            draft_id = uuid4()
            inquiry_id = uuid4()
            await connection.execute(
                """
                INSERT INTO animals
                    (id, organization_id, name, status, is_adoptable, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', true, now(), now())
                """,
                animal_id,
                organization_id,
                name,
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
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, 'specific_animal', $5, $6, '{}'::jsonb, '0912345678',
                        'closed', $7, now(), now())
                """,
                inquiry_id,
                organization_id,
                draft_id,
                adopter_user_id,
                animal_id,
                name,
                datetime.now(timezone.utc),
            )
            inquiry_ids.append(inquiry_id)
        await connection.execute("COMMIT")
    finally:
        await connection.close()
    return inquiry_ids


async def _cleanup(*, organization_id, adopter_user_id, line_user_id) -> None:
    cleanup = await asyncpg.connect(_database_url())
    try:
        await cleanup.execute("BEGIN")
        await cleanup.execute(
            "DELETE FROM growth_diary_entries WHERE organization_id = $1", organization_id
        )
        await cleanup.execute(
            "DELETE FROM growth_diary_drafts WHERE adopter_user_id = $1", adopter_user_id
        )
        await cleanup.execute(
            "DELETE FROM adoption_inquiries WHERE organization_id = $1", organization_id
        )
        await cleanup.execute(
            "DELETE FROM adoption_drafts WHERE organization_id = $1", organization_id
        )
        await cleanup.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        await cleanup.execute(
            "DELETE FROM line_user_bindings WHERE line_user_id = $1", line_user_id
        )
        await cleanup.execute("DELETE FROM users WHERE id = $1", adopter_user_id)
        await cleanup.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await cleanup.execute("COMMIT")
    finally:
        await cleanup.close()


def test_growth_diary_without_any_inquiry_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-no-inquiry")
    get_settings.cache_clear()
    line_user_id = f"Udiary{uuid4().hex}"
    try:
        client = TestClient(app)
        response = _signed_post(
            client, [_event(line_user_id, data="action=start_growth_diary&flow=growth_diary")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("請先透過「領養媒合」完成一次領養意願" in m.get("text", "") for m in messages)
    finally:
        get_settings.cache_clear()


def test_growth_diary_single_inquiry_then_text_note_saves_entry(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-single")
    get_settings.cache_clear()
    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    asyncio.run(
        _insert_adopter_with_inquiries(
            organization_id=organization_id,
            adopter_user_id=adopter_user_id,
            line_user_id=line_user_id,
            animal_specs=[(animal_id, "旺來")],
        )
    )
    try:
        client = TestClient(app)
        response = _signed_post(
            client, [_event(line_user_id, data="action=start_growth_diary&flow=growth_diary")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("旺來" in m.get("text", "") for m in messages)

        response = _signed_post(
            client, [_event(line_user_id, text="今天量體重 5 公斤，活動力很好！")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("已記錄" in m.get("text", "") for m in messages)

        async def _verify() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                entry = await connection.fetchrow(
                    "SELECT * FROM growth_diary_entries WHERE organization_id = $1",
                    organization_id,
                )
                assert entry is not None
                assert entry["note"] == "今天量體重 5 公斤，活動力很好！"
                assert entry["animal_id"] == animal_id
                pending = await connection.fetchrow(
                    "SELECT * FROM growth_diary_drafts WHERE adopter_user_id = $1",
                    adopter_user_id,
                )
                assert pending is None
            finally:
                await connection.close()

        asyncio.run(_verify())
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
        get_settings.cache_clear()


def test_growth_diary_multiple_inquiries_offers_a_picker(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-multi")
    get_settings.cache_clear()
    organization_id, adopter_user_id = uuid4(), uuid4()
    animal_id_a, animal_id_b = uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    inquiry_ids = asyncio.run(
        _insert_adopter_with_inquiries(
            organization_id=organization_id,
            adopter_user_id=adopter_user_id,
            line_user_id=line_user_id,
            animal_specs=[(animal_id_a, "旺來"), (animal_id_b, "小花")],
        )
    )
    try:
        client = TestClient(app)
        response = _signed_post(
            client, [_event(line_user_id, data="action=start_growth_diary&flow=growth_diary")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        flex = next(m for m in messages if m.get("type") == "flex")
        assert flex["contents"]["type"] == "carousel"
        assert len(flex["contents"]["contents"]) == 2

        chosen_inquiry_id = inquiry_ids[0]
        response = _signed_post(
            client,
            [
                _event(
                    line_user_id,
                    data=f"action=select_growth_diary_animal&flow=growth_diary&value={chosen_inquiry_id}",
                )
            ],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("旺來" in m.get("text", "") for m in messages)

        async def _verify_pending_points_to_choice() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                pending = await connection.fetchrow(
                    "SELECT * FROM growth_diary_drafts WHERE adopter_user_id = $1",
                    adopter_user_id,
                )
                assert pending is not None
                assert pending["inquiry_id"] == chosen_inquiry_id
                assert pending["animal_id"] == animal_id_a
            finally:
                await connection.close()

        asyncio.run(_verify_pending_points_to_choice())
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
        get_settings.cache_clear()


def test_growth_diary_cancel_clears_pending_without_saving_entry(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-cancel")
    get_settings.cache_clear()
    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    asyncio.run(
        _insert_adopter_with_inquiries(
            organization_id=organization_id,
            adopter_user_id=adopter_user_id,
            line_user_id=line_user_id,
            animal_specs=[(animal_id, "旺來")],
        )
    )
    try:
        client = TestClient(app)
        _signed_post(
            client, [_event(line_user_id, data="action=start_growth_diary&flow=growth_diary")]
        )
        response = _signed_post(client, [_event(line_user_id, text="取消")])
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("已取消這次成長日記紀錄" in m.get("text", "") for m in messages)

        async def _verify_no_entry_and_no_pending() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                entry = await connection.fetchrow(
                    "SELECT * FROM growth_diary_entries WHERE organization_id = $1",
                    organization_id,
                )
                assert entry is None
                pending = await connection.fetchrow(
                    "SELECT * FROM growth_diary_drafts WHERE adopter_user_id = $1",
                    adopter_user_id,
                )
                assert pending is None
            finally:
                await connection.close()

        asyncio.run(_verify_no_entry_and_no_pending())
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
        get_settings.cache_clear()
