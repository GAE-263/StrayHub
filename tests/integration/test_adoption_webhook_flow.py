from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from services.api.app.api import line_webhook
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
            # Skip the free-text self-introduction step (方向 D) and fall
            # back to the one-by-one questions below.
            "action=finish_freetext_profile&flow=adoption",
        ]
        actions.extend(
            f"action=answer&flow=adoption&question={question}&value={value}"
            for question, value in (
                ("housing_type", "apartment_small"),
                ("dog_experience", "first_time"),
                ("other_pets", "none"),
                ("household_members", "adults_only"),
                ("work_schedule", "work_from_home"),
                ("parenting_style", "structured"),
                ("patience_level", "high_patience"),
                ("adoption_motivation", "companionship"),
            )
        )
        actions.append("action=confirm_answers&flow=adoption")
        for action in actions:
            result = _post(client, [_event(line_user_id, action)]).json()["event_results"][0]
            assert result["status"] == "processed", result
        for value in ("王小明", "平日白天", "0911222333"):
            result = _post(client, [_text_event(line_user_id, value)]).json()["event_results"][0]
            assert result["status"] == "processed", result
        for key, value in (
            ("adopter_name", "陳小明"),
            ("contact_time", "假日下午"),
            ("phone_number", "0987654321"),
        ):
            result = _post(
                client, [_event(line_user_id, f"action=edit_contact&flow=adoption&value={key}")]
            ).json()["event_results"][0]
            assert result["status"] == "processed", result
            # Re-entering the flow resumes the edit, without repeating AI.
            assert (
                _post(
                    client, [_event(line_user_id, "action=start_adoption_matching&flow=adoption")]
                ).json()["event_results"][0]["status"]
                == "processed"
            )
            if key == "phone_number":
                invalid = _post(client, [_text_event(line_user_id, "123")]).json()["event_results"][
                    0
                ]
                assert invalid["reason"] == "invalid_phone_number"
            assert (
                _post(client, [_text_event(line_user_id, value)]).json()["event_results"][0][
                    "status"
                ]
                == "processed"
            )
        assert (
            _post(
                client,
                [_event(line_user_id, "action=edit_contact&flow=adoption&value=adopter_name")],
            ).json()["event_results"][0]["status"]
            == "processed"
        )
        assert (
            _post(
                client, [_event(line_user_id, "action=cancel_contact_edit&flow=adoption")]
            ).json()["event_results"][0]["status"]
            == "processed"
        )
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
                assert inquiry["adopter_name"] == "陳小明"
                assert inquiry["phone_number"] == "0987654321"
                assert json.loads(inquiry["answers"])["contact_time"] == "假日下午"
                assert inquiry["status"] == "new"
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_line_transport(monkeypatch):
    monkeypatch.setattr(line_webhook.LineMessagingApiAdapter, "reply", AsyncMock())
    monkeypatch.setattr(line_webhook.LineMessagingApiAdapter, "push", AsyncMock())
    monkeypatch.setattr(line_webhook.LineMessagingApiAdapter, "link_rich_menu", AsyncMock())
    monkeypatch.setattr(line_webhook, "_build_gemini_client", lambda settings: None)


def test_switching_flow_preserves_adoption_and_routes_volunteer_note(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id, membership_id, care_id = uuid4(), uuid4(), uuid4(), uuid4()
    line_user_id = f"Umixed{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    client = TestClient(app)

    def send(data):
        return _post(client, [_event(line_user_id, data)]).json()["event_results"][0]

    async def seed_care():
        connection = await asyncpg.connect(_database_url())
        try:
            user_id = await connection.fetchval(
                "SELECT user_id FROM line_user_bindings WHERE line_user_id=$1", line_user_id
            )
            await connection.execute(
                """INSERT INTO organization_memberships
                (id,organization_id,user_id,role,status,valid_from,expires_at,created_at,updated_at)
                VALUES ($1,$2,$3,'VOLUNTEER','active',now()-interval '1 day',
                        now()+interval '1 day',now(),now())""",
                membership_id,
                organization_id,
                user_id,
            )
            application_id = uuid4()
            await connection.execute(
                """INSERT INTO volunteer_applications
                (id,organization_id,user_id,status,source_channel,submitted_at,
                 decided_at,decided_by_user_id,created_at,updated_at)
                VALUES ($1,$2,$3,'approved','liff',now(),now(),$3,now(),now())""",
                application_id,
                organization_id,
                user_id,
            )
            await connection.execute(
                """INSERT INTO volunteer_access_grants
                (id,organization_id,user_id,membership_id,application_id,status,
                 valid_from,expires_at,approved_at,source_type,created_at,updated_at)
                VALUES ($1,$2,$3,$4,$5,'active',now()-interval '1 day',
                        now()+interval '1 day',now(),'manager_approval',now(),now())""",
                uuid4(),
                organization_id,
                user_id,
                membership_id,
                application_id,
            )
            await connection.execute(
                """INSERT INTO care_report_drafts
                (id,organization_id,volunteer_user_id,membership_id,animal_id,opaque_token_digest,
                 current_step,answers,status,last_interaction_at,expires_at,created_at,updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,'awaiting_note','{}','active',now(),
                        now()+interval '1 day',now(),now())""",
                care_id,
                organization_id,
                user_id,
                membership_id,
                animal_id,
                uuid4().hex,
            )
        finally:
            await connection.close()

    async def inspect_and_cleanup(cleanup=False):
        connection = await asyncpg.connect(_database_url())
        try:
            if cleanup:
                await connection.execute("DELETE FROM care_report_drafts WHERE id=$1", care_id)
                await connection.execute(
                    "DELETE FROM webhook_sessions WHERE organization_id=$1", organization_id
                )
                await connection.execute(
                    "DELETE FROM volunteer_access_grants WHERE organization_id=$1", organization_id
                )
                await connection.execute(
                    "DELETE FROM volunteer_applications WHERE organization_id=$1", organization_id
                )
                await connection.execute(
                    "DELETE FROM organization_memberships WHERE id=$1", membership_id
                )
            else:
                assert (
                    await connection.fetchval(
                        "SELECT note FROM care_report_drafts WHERE id=$1", care_id
                    )
                    == "今天走得很穩"
                )
                assert (
                    await connection.fetchval(
                        "SELECT current_step FROM adoption_drafts d "
                        "JOIN line_user_bindings b ON b.user_id=d.adopter_user_id "
                        "WHERE b.line_user_id=$1",
                        line_user_id,
                    )
                    == "selecting_organization"
                )
        finally:
            await connection.close()

    try:
        assert send("action=start_adoption_matching&flow=adoption")["status"] == "processed"
        asyncio.run(seed_care())
        result = send("action=start_care_report")
        assert result["status"] == "processed", result
        result = _post(client, [_text_event(line_user_id, "今天走得很穩")]).json()["event_results"][
            0
        ]
        assert result["status"] == "processed", result
        asyncio.run(inspect_and_cleanup())
        assert (
            send("action=select_region&flow=adoption&value=north")["reason"] == "line_flow_mismatch"
        )
        assert send("action=back_to_default_menu")["status"] == "processed"
        assert (
            _post(client, [_text_event(line_user_id, "不應寫入")]).json()["event_results"][0][
                "reason"
            ]
            == "line_flow_required"
        )
        assert send("action=start_adoption_matching&flow=adoption")["status"] == "processed"
        image_event = {
            "type": "message",
            "webhookEventId": uuid4().hex,
            "source": {"userId": line_user_id},
            "message": {"type": "image", "id": "test-image"},
        }
        assert _post(client, [image_event]).json()["event_results"][0]["status"] == "processed"
        asyncio.run(inspect_and_cleanup())
    finally:
        asyncio.run(inspect_and_cleanup(cleanup=True))
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_adoption_browse_paginates_searches_and_revalidates_selection(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id, other_org, other_animal = uuid4(), uuid4(), uuid4(), uuid4()
    line_user_id = f"Ubrowse{uuid4().hex}"
    extra_ids = [uuid4() for _ in range(13)]
    asyncio.run(_seed(organization_id, animal_id))
    asyncio.run(_seed(other_org, other_animal))

    async def add_animals():
        connection = await asyncpg.connect(_database_url())
        try:
            for i, aid in enumerate(extra_ids):
                await connection.execute(
                    """INSERT INTO animals
                    (id,organization_id,name,shelter_number,status,is_adoptable,created_at,updated_at)
                    VALUES ($1,$2,$3,$4,'active',true,now(),now())""",
                    aid,
                    organization_id,
                    f"測試犬{i:02}",
                    f"B{i:03}",
                )
        finally:
            await connection.close()

    client = TestClient(app)

    def send(data=None, text=None):
        event = _event(line_user_id, data) if data else _text_event(line_user_id, text)
        event["replyToken"] = "test-reply"
        result = _post(client, [event]).json()["event_results"][0]
        assert result["status"] == "processed", result
        return line_webhook.LineMessagingApiAdapter.reply.call_args.kwargs["messages"]

    try:
        asyncio.run(add_animals())
        send("action=start_adoption_matching&flow=adoption")
        send(f"action=select_organization&flow=adoption&value={organization_id}")
        messages = send("action=choose_path&flow=adoption&value=specific_animal")
        assert "共 14 隻" in messages[0]["text"]
        assert len(messages[1]["contents"]["contents"]) == 12
        assert str(other_animal) not in json.dumps(messages)
        messages = send(text="測試犬")
        assert "共 13 隻" in messages[0]["text"]
        messages = send("action=browse_animals&flow=adoption&page=2&query=測試犬")
        assert "第 2／2 頁" in messages[0]["text"]
        assert str(extra_ids[-1]) in json.dumps(messages)
        messages = send(text="%")
        assert "找不到" in messages[0]["text"]
        assert "返回全部清單" in json.dumps(messages, ensure_ascii=False)
        messages = send(text="B012")
        assert "共 1 隻" in messages[0]["text"]
        send(f"action=select_target_animal&flow=adoption&value={extra_ids[-1]}")

        async def deactivate():
            connection = await asyncpg.connect(_database_url())
            try:
                await connection.execute(
                    "UPDATE animals SET is_adoptable=false WHERE id=$1", extra_ids[-1]
                )
            finally:
                await connection.close()

        asyncio.run(deactivate())
        result = _post(
            client, [_event(line_user_id, "action=confirm_target_animal&flow=adoption")]
        ).json()["event_results"][0]
        assert result["reason"] == "animal_not_adoptable"
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        asyncio.run(_cleanup(other_org, ()))
        get_settings.cache_clear()


def test_repeated_old_question_click_refreshes_current_question(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Urepeat{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    client = TestClient(app)

    def send(data):
        event = _event(line_user_id, data)
        event["replyToken"] = "test-reply"
        result = _post(client, [event]).json()["event_results"][0]
        assert result["status"] == "processed", result
        return line_webhook.LineMessagingApiAdapter.reply.call_args.kwargs["messages"]

    def find_action_data(value, fragment):
        if isinstance(value, dict):
            data = value.get("data")
            if isinstance(data, str) and fragment in data:
                return data
            for child in value.values():
                if found := find_action_data(child, fragment):
                    return found
        elif isinstance(value, list):
            for child in value:
                if found := find_action_data(child, fragment):
                    return found
        return None

    try:
        send("action=start_adoption_matching&flow=adoption")
        send(f"action=select_organization&flow=adoption&value={organization_id}")
        send("action=choose_path&flow=adoption&value=specific_animal")
        send(f"action=select_target_animal&flow=adoption&value={animal_id}")
        send("action=confirm_target_animal&flow=adoption")
        send("action=finish_freetext_profile&flow=adoption")
        answers = (
            ("housing_type", "apartment_small"),
            ("dog_experience", "first_time"),
            ("other_pets", "none"),
            ("household_members", "adults_only"),
            ("work_schedule", "work_from_home"),
        )
        messages = None
        for question, value in answers:
            messages = send(f"action=answer&flow=adoption&question={question}&value={value}")

        assert messages is not None
        repeated = find_action_data(messages, "question=parenting_style")
        assert repeated is not None and "version=" in repeated
        send(repeated)
        send(repeated)

        messages = line_webhook.LineMessagingApiAdapter.reply.call_args.kwargs["messages"]
        assert "耐心" in json.dumps(messages, ensure_ascii=False)

        async def verify():
            connection = await asyncpg.connect(_database_url())
            try:
                row = await connection.fetchrow(
                    """SELECT current_step, answers FROM adoption_drafts d
                    JOIN line_user_bindings b ON b.user_id=d.adopter_user_id
                    WHERE b.line_user_id=$1 AND d.status='active'""",
                    line_user_id,
                )
                assert row["current_step"] == "answering_patience"
                stored = json.loads(row["answers"])
                assert stored["parenting_style"] == "structured"
                assert "patience_level" not in stored
            finally:
                await connection.close()

        asyncio.run(verify())

        back = find_action_data(messages, "action=back")
        assert back is not None and "step=answering_patience" in back and "version=" in back
        send(back)
        send(back)

        async def verify_repeated_back():
            connection = await asyncpg.connect(_database_url())
            try:
                step = await connection.fetchval(
                    """SELECT current_step FROM adoption_drafts d
                    JOIN line_user_bindings b ON b.user_id=d.adopter_user_id
                    WHERE b.line_user_id=$1 AND d.status='active'""",
                    line_user_id,
                )
                assert step == "answering_parenting_style"
            finally:
                await connection.close()

        asyncio.run(verify_repeated_back())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_saved_current_answer_is_reconfirmed_and_next_question_is_shown(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Uresumeanswer{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    client = TestClient(app)

    def send(data):
        event = _event(line_user_id, data)
        event["replyToken"] = "test-reply"
        result = _post(client, [event]).json()["event_results"][0]
        assert result["status"] == "processed", result
        return line_webhook.LineMessagingApiAdapter.reply.call_args.kwargs["messages"]

    def find_action_data(value, fragment):
        if isinstance(value, dict):
            data = value.get("data")
            if isinstance(data, str) and fragment in data:
                return data
            for child in value.values():
                if found := find_action_data(child, fragment):
                    return found
        elif isinstance(value, list):
            for child in value:
                if found := find_action_data(child, fragment):
                    return found
        return None

    async def save_answer_without_advancing():
        connection = await asyncpg.connect(_database_url())
        try:
            await connection.execute(
                """UPDATE adoption_drafts d
                SET answers = (answers::jsonb || '{"other_pets": "none"}'::jsonb)::json
                FROM line_user_bindings b
                WHERE b.user_id=d.adopter_user_id AND b.line_user_id=$1
                  AND d.current_step='answering_other_pets'""",
                line_user_id,
            )
        finally:
            await connection.close()

    try:
        send("action=start_adoption_matching&flow=adoption")
        send(f"action=select_organization&flow=adoption&value={organization_id}")
        send("action=choose_path&flow=adoption&value=specific_animal")
        send(f"action=select_target_animal&flow=adoption&value={animal_id}")
        send("action=confirm_target_animal&flow=adoption")
        send("action=finish_freetext_profile&flow=adoption")
        messages = send("action=answer&flow=adoption&question=housing_type&value=apartment_small")
        experience = find_action_data(messages, "question=dog_experience")
        assert experience is not None
        messages = send(experience)
        has_cats = find_action_data(messages, "value=has_cats")
        assert has_cats is not None

        asyncio.run(save_answer_without_advancing())
        messages = send(has_cats)

        rendered = json.dumps(messages, ensure_ascii=False)
        assert "家裡平常有誰在呢" in rendered
        assert "目前步驟已完成" not in rendered

        async def verify():
            connection = await asyncpg.connect(_database_url())
            try:
                row = await connection.fetchrow(
                    """SELECT current_step, answers FROM adoption_drafts d
                    JOIN line_user_bindings b ON b.user_id=d.adopter_user_id
                    WHERE b.line_user_id=$1 AND d.status='active'""",
                    line_user_id,
                )
                assert row["current_step"] == "answering_household"
                assert json.loads(row["answers"])["other_pets"] == "has_cats"
            finally:
                await connection.close()

        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()


def test_incomplete_legacy_draft_returns_to_missing_question_without_500(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-adoption-webhook")
    get_settings.cache_clear()
    organization_id, animal_id = uuid4(), uuid4()
    line_user_id = f"Uincomplete{uuid4().hex}"
    asyncio.run(_seed(organization_id, animal_id))
    client = TestClient(app)

    def send(data):
        event = _event(line_user_id, data)
        event["replyToken"] = "test-reply"
        return _post(client, [event]).json()["event_results"][0]

    async def corrupt_to_observed_legacy_shape():
        connection = await asyncpg.connect(_database_url())
        try:
            await connection.execute(
                """UPDATE adoption_drafts d
                SET current_step='answering_adoption_motivation',
                    answers=$2::jsonb, interaction_version=12
                FROM line_user_bindings b
                WHERE b.user_id=d.adopter_user_id AND b.line_user_id=$1""",
                line_user_id,
                json.dumps(
                    {
                        "dog_experience": "first_time",
                        "other_pets": "none",
                        "household_members": "adults_only",
                        "work_schedule": "work_from_home",
                        "parenting_style": "structured",
                        "patience_level": "high_patience",
                    }
                ),
            )
        finally:
            await connection.close()

    async def verify():
        connection = await asyncpg.connect(_database_url())
        try:
            row = await connection.fetchrow(
                """SELECT current_step, answers FROM adoption_drafts d
                JOIN line_user_bindings b ON b.user_id=d.adopter_user_id
                WHERE b.line_user_id=$1 AND d.status='active'""",
                line_user_id,
            )
            assert row["current_step"] == "answering_housing"
            answers = json.loads(row["answers"])
            assert answers["parenting_style"] == "structured"
            assert "housing_type" not in answers
        finally:
            await connection.close()

    try:
        assert send("action=start_adoption_matching&flow=adoption")["status"] == "processed"
        assert (
            send(f"action=select_organization&flow=adoption&value={organization_id}")["status"]
            == "processed"
        )
        assert send("action=choose_path&flow=adoption&value=specific_animal")["status"] == (
            "processed"
        )
        assert (
            send(f"action=select_target_animal&flow=adoption&value={animal_id}")["status"]
            == "processed"
        )
        assert send("action=confirm_target_animal&flow=adoption")["status"] == "processed"
        asyncio.run(corrupt_to_observed_legacy_shape())

        result = send("action=start_adoption_matching&flow=adoption")
        assert result["status"] == "processed", result
        messages = line_webhook.LineMessagingApiAdapter.reply.call_args.kwargs["messages"]
        assert "還有題目未完成" in messages[0]["text"]
        assert "你家是什麼樣子" in json.dumps(messages[1], ensure_ascii=False)
        asyncio.run(verify())
    finally:
        asyncio.run(_cleanup(organization_id, (line_user_id,)))
        get_settings.cache_clear()
