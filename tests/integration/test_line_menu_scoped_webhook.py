"""Real signature + real isolated DB; LINE transport only is replaced."""

import asyncio
import base64
import hashlib
import hmac
import json
import os
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from services.api.app.api import line_webhook
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.main import app
from services.api.app.persistence.database.engine import engine

from tests.unit.test_line_menu_smoke_scope import BOT, UID, scoped_settings


class SyntheticLine(MockLineAdapter):
    def __init__(self):
        super().__init__()
        self.links = []
        self.allowed = {UID, "U" + "3" * 32}

    def ensure_recipient_allowed(self, uid):
        assert uid in self.allowed

    async def link_rich_menu(self, *, rich_menu_id, user_id=None):
        assert user_id is not None  # No global/default operations allowed.
        self.links.append((user_id, rich_menu_id))


@pytest.mark.parametrize(
    "uid,bot,signature_valid,expected",
    [
        (UID, BOT, True, 1),
        ("U" + "3" * 32, BOT, True, 0),
        (UID, "wrong-bot", True, 0),
        (UID, BOT, False, 0),
    ],
)
def test_real_signed_webhook_scope_and_duplicate_claim(
    monkeypatch, uid, bot, signature_valid, expected
):
    settings = scoped_settings(
        line_channel_secret="synthetic-webhook-secret",
        line_rich_menu_adoption_hub_id="richmenu-synthetic-hub",
    )
    line = SyntheticLine()
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)
    monkeypatch.setattr(line_webhook, "LineMessagingApiAdapter", lambda: line)
    event_id = uuid4().hex
    event = {
        "type": "postback",
        "webhookEventId": event_id,
        "replyToken": "synthetic",
        "source": {"type": "user", "userId": uid},
        "postback": {"data": "action=open_adoption_hub"},
    }
    raw = json.dumps({"destination": bot, "events": [event]}).encode()
    signature = base64.b64encode(
        hmac.new(settings.line_channel_secret.encode(), raw, hashlib.sha256).digest()
    ).decode()
    asyncio.run(engine.dispose(close=False))
    client = TestClient(app)
    try:
        response = client.post(
            "/v1/line/webhook",
            content=raw,
            headers={"X-Line-Signature": signature if signature_valid else "bad"},
        )
        assert response.status_code == (200 if signature_valid else 401)
        assert len(line.links) == expected
        if signature_valid:
            asyncio.run(engine.dispose(close=False))
            repeated = client.post(
                "/v1/line/webhook", content=raw, headers={"X-Line-Signature": signature}
            )
            assert repeated.status_code == 200
            assert len(line.links) == expected
            assert "duplicate_ignored" in repeated.text
        assert line.pushes == []
        assert line.unlinked_users == []
    finally:

        async def cleanup():
            connection = await asyncpg.connect(os.environ["STRAYHUB_TEST_DATABASE_URL"])
            try:
                await connection.execute(
                    "DELETE FROM line_webhook_events WHERE webhook_event_id=$1", event_id
                )
            finally:
                await connection.close()

        asyncio.run(cleanup())
        asyncio.run(engine.dispose(close=False))


def test_scoped_hub_return_and_adoption_entry_keep_domain_checks(monkeypatch):
    test_uid = "U" + uuid4().hex
    other_uid = "U" + uuid4().hex
    settings = scoped_settings(
        line_role_menu_test_user_sha256=hashlib.sha256(test_uid.encode()).hexdigest(),
        line_channel_secret="synthetic-webhook-secret",
        line_rich_menu_adoption_hub_id="richmenu-synthetic-hub",
        line_rich_menu_default_id="richmenu-synthetic-default",
    )
    line = SyntheticLine()
    line.allowed = {test_uid, other_uid}
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)
    monkeypatch.setattr(line_webhook, "LineMessagingApiAdapter", lambda: line)
    event_ids = []
    client = TestClient(app)

    def send(action, uid=test_uid):
        event_id = uuid4().hex
        event_ids.append(event_id)
        raw = json.dumps(
            {
                "destination": BOT,
                "events": [
                    {
                        "type": "postback",
                        "webhookEventId": event_id,
                        "replyToken": "synthetic",
                        "source": {"type": "user", "userId": uid},
                        "postback": {"data": action},
                    }
                ],
            }
        ).encode()
        signature = base64.b64encode(
            hmac.new(settings.line_channel_secret.encode(), raw, hashlib.sha256).digest()
        ).decode()
        asyncio.run(engine.dispose(close=False))
        result = client.post(
            "/v1/line/webhook", content=raw, headers={"X-Line-Signature": signature}
        )
        assert result.status_code == 200

    async def count_and_cleanup():
        connection = await asyncpg.connect(os.environ["STRAYHUB_TEST_DATABASE_URL"])
        try:
            rows = await connection.fetch(
                "SELECT user_id FROM line_user_bindings WHERE line_user_id=$1", test_uid
            )
            assert len(rows) == 1
            user_id = rows[0]["user_id"]
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM adoption_drafts WHERE adopter_user_id=$1", user_id
                )
                == 1
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM line_user_bindings WHERE line_user_id=$1", other_uid
                )
                == 0
            )
            await connection.execute(
                "DELETE FROM adoption_drafts WHERE adopter_user_id=$1", user_id
            )
            await connection.execute("DELETE FROM line_user_bindings WHERE user_id=$1", user_id)
            await connection.execute("DELETE FROM users WHERE id=$1", user_id)
            await connection.execute(
                "DELETE FROM line_webhook_events WHERE webhook_event_id=ANY($1::text[])", event_ids
            )
        finally:
            await connection.close()

    try:
        send("action=open_adoption_hub")
        send("action=back_to_default_menu")
        assert line.links == [
            (test_uid, "richmenu-synthetic-hub"),
            (test_uid, "richmenu-synthetic-default"),
        ]
        send("action=start_growth_diary&flow=growth_diary")
        # Test mode does not manufacture an adoption completion or diary permission.
        assert "完成一次領養意願" in str(line.replies[-1])
        send("action=start_adoption_matching&flow=adoption", other_uid)
        assert "尚未開放" in str(line.replies[-1])
        send("action=start_adoption_matching&flow=adoption")
        assert "尚未開放" not in str(line.replies[-1])
        # Opening the hub again must not be mistaken for a care-report postback
        # merely because an adoption draft/current_flow already exists.
        send("action=open_adoption_hub")
        assert line.links[-1] == (test_uid, "richmenu-synthetic-hub")
        assert len(line.links) == 3
        assert not line.pushes
    finally:
        asyncio.run(count_and_cleanup())
        asyncio.run(engine.dispose(close=False))
