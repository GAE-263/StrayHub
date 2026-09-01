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


def _event(line_user_id: str, data: str, *, event_id: str | None = None) -> dict:
    return {
        "type": "postback",
        "webhookEventId": event_id or uuid4().hex,
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


async def _seed(organization_id: UUID, animal_id: UUID, *, region: str = "north") -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, region, status, created_at, updated_at)
            VALUES ($1, 'Webhook Adoption Shelter', $2, $3, 'active', now(), now())
            """,
            organization_id,
            f"WEBHOOK-{organization_id.hex[:8]}",
            region,
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, is_adoptable,
                 size, energy, temperament, created_at, updated_at)
            VALUES ($1, $2, '旺來', 'A100', 'active', true,
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


def test_entry_resumes_one_draft_and_duplicate_event_is_idempotent(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        event_id = uuid4().hex
        first = _post(
            client,
            [
                _event(
                    line_user_id,
                    "action=start_adoption_matching&flow=adoption",
                    event_id=event_id,
                )
            ],
        )
        duplicate = _post(
            client,
            [
                _event(
                    line_user_id,
                    "action=start_adoption_matching&flow=adoption",
                    event_id=event_id,
                )
            ],
        )
        resume = _post(
            client,
            [_event(line_user_id, "action=start_adoption_matching&flow=adoption")],
        )

        assert first.json()["event_results"][0]["status"] == "processed"
        assert duplicate.json()["event_results"][0]["status"] == "duplicate_ignored"
        assert resume.json()["event_results"][0]["status"] == "processed"

        async def verify() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                assert (
                    await connection.fetchval(
                        """
                    SELECT count(*) FROM adoption_drafts d
                    JOIN line_user_bindings b ON b.user_id = d.adopter_user_id
                    WHERE b.line_user_id = $1
                    """,
                        line_user_id,
                    )
                    == 1
                )
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_other_line_user_cannot_operate_an_existing_draft(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    owner = f"Uowner{uuid4().hex}"
    stranger = f"Ustranger{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
        assert (
            _post(client, [_event(owner, "action=start_adoption_matching&flow=adoption")]).json()[
                "event_results"
            ][0]["status"]
            == "processed"
        )

        response = _post(
            client,
            [_event(stranger, f"action=select_organization&flow=adoption&value={organization_id}")],
        )
        assert response.json()["event_results"][0] == {
            "webhook_event_id": response.json()["event_results"][0]["webhook_event_id"],
            "status": "rejected",
            "reason": "line_binding_required",
        }

        async def verify() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                row = await connection.fetchrow(
                    """
                    SELECT d.organization_id, b.line_user_id FROM adoption_drafts d
                    JOIN line_user_bindings b ON b.user_id = d.adopter_user_id
                    WHERE d.status = 'active' AND b.line_user_id = $1
                    """,
                    owner,
                )
                assert row["line_user_id"] == owner
                assert row["organization_id"] is None
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (owner, stranger)))
        get_settings.cache_clear()


def test_selected_shelter_cannot_use_animal_id_from_another_shelter(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    other_organization_id, other_animal_id = uuid4(), uuid4()
    line_user_id = f"Utenant{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    asyncio.run(_seed(other_organization_id, other_animal_id))
    try:
        client = TestClient(app)
        for action in (
            "action=start_adoption_matching&flow=adoption",
            f"action=select_organization&flow=adoption&value={organization_id}",
            "action=choose_path&flow=adoption&value=specific_animal",
        ):
            result = _post(client, [_event(line_user_id, action)]).json()["event_results"][0]
            assert result["status"] == "processed", result

        result = _post(
            client,
            [
                _event(
                    line_user_id,
                    f"action=select_target_animal&flow=adoption&value={other_animal_id}",
                )
            ],
        ).json()["event_results"][0]
        assert result["status"] == "rejected"
        assert result["reason"] == "animal_not_adoptable"
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        asyncio.run(_cleanup(other_organization_id, ()))
        get_settings.cache_clear()


def test_specific_animal_flow_submits_without_optional_ai(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Uflow{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    try:
        client = TestClient(app)
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

        async def verify() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                inquiry = await connection.fetchrow(
                    "SELECT * FROM adoption_inquiries WHERE organization_id = $1",
                    organization_id,
                )
                assert inquiry["target_animal_id"] == animal_id
                assert inquiry["adopter_name"] == "王小明"
                assert inquiry["status"] == "new"
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()
