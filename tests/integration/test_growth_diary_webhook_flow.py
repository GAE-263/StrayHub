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
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiClient,
    GeminiGrowthDiaryAnalysis,
)
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
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


def _flex_texts(message: dict) -> list[str]:
    texts: list[str] = []

    def _walk(node) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and "text" in node:
                texts.append(node["text"])
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(message.get("contents"))
    return texts


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


def _capture_pushes(monkeypatch) -> list[tuple[str, list[dict]]]:
    """See test_adoption_webhook_flow.py's helper of the same name — AI
    background-task pushes never show up in `debug_replies` since they run
    strictly after the synchronous reply is already built."""
    calls: list[tuple[str, list[dict]]] = []
    original_push = MockLineAdapter.push

    async def recording_push(self, *, to_user_id: str, messages: list[dict]) -> None:
        calls.append((to_user_id, messages))
        await original_push(self, to_user_id=to_user_id, messages=messages)

    monkeypatch.setattr(MockLineAdapter, "push", recording_push)
    return calls


async def _insert_staff_member(*, organization_id, staff_user_id, staff_line_user_id) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Growth Diary Staff', 'active', now(), now())
            """,
            staff_user_id,
            f"growth-diary-staff-{staff_user_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'STAFF', 'active', now(), now())
            """,
            uuid4(),
            organization_id,
            staff_user_id,
        )
        await connection.execute(
            """
            INSERT INTO line_user_bindings
                (id, line_user_id, user_id, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', now(), now())
            """,
            uuid4(),
            staff_line_user_id,
            staff_user_id,
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


async def _cleanup(
    *, organization_id, adopter_user_id, line_user_id, staff_user_id=None, staff_line_user_id=None
) -> None:
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
        if staff_line_user_id is not None:
            await cleanup.execute(
                "DELETE FROM line_user_bindings WHERE line_user_id = $1", staff_line_user_id
            )
        if staff_user_id is not None:
            await cleanup.execute(
                "DELETE FROM organization_memberships WHERE user_id = $1", staff_user_id
            )
            await cleanup.execute("DELETE FROM users WHERE id = $1", staff_user_id)
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


def test_growth_diary_menu_tap_offers_write_or_review_choice_first(monkeypatch) -> None:
    """Tapping the Rich Menu's "毛孩日記" tile must not jump straight into
    the share flow — 回顧 lives one level under that tile as a choice, not
    beside it on the Rich Menu itself."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-choice")
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
        assert any("寫新的一篇" in str(m) for m in messages)
        assert any("日記回顧" in str(m) for m in messages)
        # No pending draft yet — the adopter hasn't chosen "寫新的一篇".
        assert not any("旺來" in str(m) for m in messages)

        async def _verify_no_pending_draft_yet() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                pending = await connection.fetchrow(
                    "SELECT * FROM growth_diary_drafts WHERE adopter_user_id = $1",
                    adopter_user_id,
                )
                assert pending is None
            finally:
                await connection.close()

        asyncio.run(_verify_no_pending_draft_yet())
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
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
        assert any("寫新的一篇" in str(m) for m in messages)

        response = _signed_post(
            client,
            [_event(line_user_id, data="action=start_growth_diary_entry&flow=growth_diary")],
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
        _signed_post(
            client, [_event(line_user_id, data="action=start_growth_diary&flow=growth_diary")]
        )
        response = _signed_post(
            client,
            [_event(line_user_id, data="action=start_growth_diary_entry&flow=growth_diary")],
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
        _signed_post(
            client,
            [_event(line_user_id, data="action=start_growth_diary_entry&flow=growth_diary")],
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


def test_growth_diary_concern_entry_pushes_ai_reply_and_alerts_staff(monkeypatch) -> None:
    """One Gemini call, two different outputs: the adopter gets a warm reply
    pushed, and a "concern" mood also alerts every STAFF member with a LINE
    binding in the organization — not just a passive write to the back
    office record."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-concern")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    async def fake_analyze_growth_diary_entry(self, prompt: str) -> GeminiGrowthDiaryAnalysis:
        return GeminiGrowthDiaryAnalysis(
            mood="concern",
            adopter_reply="聽起來牠可能不太舒服，建議帶去給獸醫看看喔 🩺",
            staff_summary="疑似食慾不振與精神不佳，建議追蹤。",
        )

    monkeypatch.setattr(GeminiClient, "analyze_growth_diary_entry", fake_analyze_growth_diary_entry)

    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    staff_user_id = uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    staff_line_user_id = f"Ustaff{uuid4().hex}"
    asyncio.run(
        _insert_adopter_with_inquiries(
            organization_id=organization_id,
            adopter_user_id=adopter_user_id,
            line_user_id=line_user_id,
            animal_specs=[(animal_id, "旺來")],
        )
    )
    asyncio.run(
        _insert_staff_member(
            organization_id=organization_id,
            staff_user_id=staff_user_id,
            staff_line_user_id=staff_line_user_id,
        )
    )
    try:
        client = TestClient(app)
        _signed_post(
            client, [_event(line_user_id, data="action=start_growth_diary&flow=growth_diary")]
        )
        _signed_post(
            client,
            [_event(line_user_id, data="action=start_growth_diary_entry&flow=growth_diary")],
        )
        response = _signed_post(
            client, [_event(line_user_id, text="牠這幾天都不太吃東西，感覺沒什麼精神")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("AI 小幫手正在看看" in m.get("text", "") for m in messages)

        assert len(pushes) == 2
        pushes_by_recipient = {to_user_id: msgs for to_user_id, msgs in pushes}
        adopter_texts = [
            text for msg in pushes_by_recipient[line_user_id] for text in _flex_texts(msg)
        ]
        assert any("建議帶去給獸醫看看" in text for text in adopter_texts)
        staff_texts = [m.get("text", "") for m in pushes_by_recipient[staff_line_user_id]]
        assert any("疑似食慾不振與精神不佳" in text for text in staff_texts)
        assert any("異常通知" in text for text in staff_texts)

        async def _verify_entry_persisted() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                entry = await connection.fetchrow(
                    "SELECT ai_mood, ai_reply, ai_staff_summary FROM growth_diary_entries "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert entry["ai_mood"] == "concern"
                assert "獸醫" in entry["ai_reply"]
                assert entry["ai_staff_summary"] == "疑似食慾不振與精神不佳，建議追蹤。"
            finally:
                await connection.close()

        asyncio.run(_verify_entry_persisted())
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
                staff_user_id=staff_user_id,
                staff_line_user_id=staff_line_user_id,
            )
        )
        get_settings.cache_clear()


def test_growth_diary_positive_entry_does_not_alert_staff(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-positive")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    async def fake_analyze_growth_diary_entry(self, prompt: str) -> GeminiGrowthDiaryAnalysis:
        return GeminiGrowthDiaryAnalysis(
            mood="positive",
            adopter_reply="看起來牠適應得很好，繼續加油！",
            staff_summary="適應良好，無需介入。",
        )

    monkeypatch.setattr(GeminiClient, "analyze_growth_diary_entry", fake_analyze_growth_diary_entry)

    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    staff_user_id = uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    staff_line_user_id = f"Ustaff{uuid4().hex}"
    asyncio.run(
        _insert_adopter_with_inquiries(
            organization_id=organization_id,
            adopter_user_id=adopter_user_id,
            line_user_id=line_user_id,
            animal_specs=[(animal_id, "旺來")],
        )
    )
    asyncio.run(
        _insert_staff_member(
            organization_id=organization_id,
            staff_user_id=staff_user_id,
            staff_line_user_id=staff_line_user_id,
        )
    )
    try:
        client = TestClient(app)
        _signed_post(
            client, [_event(line_user_id, data="action=start_growth_diary&flow=growth_diary")]
        )
        _signed_post(
            client,
            [_event(line_user_id, data="action=start_growth_diary_entry&flow=growth_diary")],
        )
        _signed_post(client, [_event(line_user_id, text="今天活動力很好，胖了一點點")])

        # Only the adopter gets pushed — no staff alert for a positive mood.
        assert len(pushes) == 1
        assert pushes[0][0] == line_user_id
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
                staff_user_id=staff_user_id,
                staff_line_user_id=staff_line_user_id,
            )
        )
        get_settings.cache_clear()


def test_growth_diary_ai_analysis_degrades_gracefully_without_credentials(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-no-ai")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_SERVICE_ACCOUNT_PATH", "")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

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
        _signed_post(
            client,
            [_event(line_user_id, data="action=start_growth_diary_entry&flow=growth_diary")],
        )
        _signed_post(client, [_event(line_user_id, text="今天量體重 5 公斤")])

        # No credentials, but a note was given — the entry is saved either
        # way; without Gemini there's simply nothing to push back.
        assert len(pushes) == 0

        async def _verify_entry_saved_without_ai_fields() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                entry = await connection.fetchrow(
                    "SELECT note, ai_mood, ai_reply FROM growth_diary_entries "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert entry["note"] == "今天量體重 5 公斤"
                assert entry["ai_mood"] is None
                assert entry["ai_reply"] is None
            finally:
                await connection.close()

        asyncio.run(_verify_entry_saved_without_ai_fields())
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
        get_settings.cache_clear()


class _AwaitableNone:
    def __await__(self):
        async def _inner() -> None:
            return None

        return _inner().__await__()


def test_growth_diary_photo_only_entry_gets_canned_reply_without_gemini_call(monkeypatch) -> None:
    """A photo with no text note skips the Gemini call entirely (this
    project's Gemini integration is text-only so far) but the adopter still
    gets a warm acknowledgement rather than silence."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-photo-only")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    def fail_if_called(self, prompt: str):
        raise AssertionError("Gemini must not be called for a photo-only entry")

    monkeypatch.setattr(GeminiClient, "analyze_growth_diary_entry", fail_if_called)

    class _FakeImageContent:
        content = b"fake-image-bytes"
        content_type = "image/jpeg"

    async def fake_get_image_content(self, *, message_id: str):
        return _FakeImageContent()

    monkeypatch.setattr(MockLineAdapter, "get_image_content", fake_get_image_content)
    monkeypatch.setattr(
        "services.api.app.application.media_service.MediaProcessingService.store_cleaned",
        lambda self, **kwargs: _AwaitableNone(),
    )

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
        _signed_post(
            client,
            [_event(line_user_id, data="action=start_growth_diary_entry&flow=growth_diary")],
        )
        _signed_post(
            client,
            [
                {
                    "webhookEventId": uuid4().hex,
                    "source": {"userId": line_user_id},
                    "replyToken": uuid4().hex,
                    "type": "message",
                    "message": {"type": "image", "id": "fake-message-id"},
                }
            ],
        )

        assert len(pushes) == 1
        _, messages = pushes[0]
        assert any("看到牠現在的樣子" in m.get("text", "") for m in messages)
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
        get_settings.cache_clear()


def test_growth_diary_view_history_lists_past_entries_newest_first(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-history")
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
        for note in ("第一篇紀錄", "第二篇紀錄"):
            _signed_post(
                client, [_event(line_user_id, data="action=start_growth_diary&flow=growth_diary")]
            )
            _signed_post(
                client,
                [_event(line_user_id, data="action=start_growth_diary_entry&flow=growth_diary")],
            )
            _signed_post(client, [_event(line_user_id, text=note)])

        response = _signed_post(
            client,
            [_event(line_user_id, data="action=view_growth_diary_history&flow=growth_diary")],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        flex = next(m for m in messages if m.get("type") == "flex")
        all_texts = _flex_texts(flex)
        assert any("第一篇紀錄" in text for text in all_texts)
        assert any("第二篇紀錄" in text for text in all_texts)
        bubbles = flex["contents"]["contents"]
        # Newest first.
        assert "第二篇紀錄" in "".join(_flex_texts({"contents": bubbles[0]}))
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
        get_settings.cache_clear()


def test_growth_diary_view_history_with_no_entries_says_so(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-history-empty")
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
            client,
            [_event(line_user_id, data="action=view_growth_diary_history&flow=growth_diary")],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("還沒有任何毛孩日記紀錄" in m.get("text", "") for m in messages)
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
        get_settings.cache_clear()


def test_growth_diary_snooze_reminder_pushes_cadence_clock(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-growth-diary-snooze")
    get_settings.cache_clear()

    organization_id, adopter_user_id, animal_id = uuid4(), uuid4(), uuid4()
    line_user_id = f"Udiary{uuid4().hex}"
    inquiry_ids = asyncio.run(
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
            client,
            [
                _event(
                    line_user_id,
                    data=(
                        "action=snooze_growth_diary_reminder&flow=growth_diary"
                        f"&value={inquiry_ids[0]}"
                    ),
                )
            ],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("晚點再提醒你" in m.get("text", "") for m in messages)

        async def _verify_clock_advanced() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                inquiry = await connection.fetchrow(
                    "SELECT last_growth_diary_prompted_at FROM adoption_inquiries WHERE id = $1",
                    inquiry_ids[0],
                )
                assert inquiry["last_growth_diary_prompted_at"] is not None
            finally:
                await connection.close()

        asyncio.run(_verify_clock_advanced())
    finally:
        asyncio.run(
            _cleanup(
                organization_id=organization_id,
                adopter_user_id=adopter_user_id,
                line_user_id=line_user_id,
            )
        )
        get_settings.cache_clear()
