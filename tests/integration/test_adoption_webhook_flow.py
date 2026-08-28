from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
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
    # TestClient does not keep one event loop alive across separate .post()
    # calls; without disposing first, the pool tries to reuse a connection
    # bound to a now-closed loop and crashes (same class of issue the rest of
    # this suite works around with `await engine.dispose(close=False)`).
    asyncio.run(engine.dispose(close=False))
    body = json.dumps({"events": events}).encode("utf-8")
    secret = get_settings().line_channel_secret
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return client.post(
        "/v1/line/webhook",
        content=body,
        headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
    )


def _postback_event(line_user_id: str, data: str) -> dict:
    # No replyToken: `_reply()` skips the real outbound call to LINE's API,
    # which is exactly what a test without network access needs.
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


async def _insert_adoption_fixtures(*, organization_id, animal_id, region=None) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, region, status, created_at, updated_at)
            VALUES ($1, 'Adoption Webhook Shelter', $2, $3, 'active', now(), now())
            """,
            organization_id,
            f"ADOPTWH-{organization_id.hex[:8]}",
            region,
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, status, is_adoptable, size, energy, temperament,
                 created_at, updated_at)
            VALUES ($1, $2, '旺來', 'active', true, 'large', 'medium', '[]'::jsonb, now(), now())
            """,
            animal_id,
            organization_id,
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


async def _insert_volunteer_fixtures(
    *, organization_id, user_id, membership_id, line_user_id
) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Adoption Webhook Regression Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"REG-{organization_id.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Webhook Regression Volunteer', 'active', now(), now())
            """,
            user_id,
            f"regression-vol-{user_id.hex[:10]}",
        )
        # STAFF (not VOLUNTEER) so this fixture only needs a plain active
        # membership — the effective-membership predicate requires an
        # additional VolunteerAccessGrant chain for VOLUNTEER, which is
        # unrelated plumbing this regression test has no need to exercise.
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'STAFF', 'active', now(), now())
            """,
            membership_id,
            organization_id,
            user_id,
        )
        await connection.execute(
            """
            INSERT INTO line_user_bindings
                (id, line_user_id, user_id, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', now(), now())
            """,
            uuid4(),
            line_user_id,
            user_id,
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


async def _cleanup_adoption(*, organization_id, line_user_id) -> None:
    cleanup = await asyncpg.connect(_database_url())
    try:
        await cleanup.execute("BEGIN")
        await cleanup.execute(
            "DELETE FROM audit_records WHERE organization_id = $1", organization_id
        )
        await cleanup.execute(
            "DELETE FROM adoption_inquiries WHERE organization_id = $1", organization_id
        )
        await cleanup.execute(
            "DELETE FROM adoption_drafts WHERE organization_id = $1 "
            "OR adopter_user_id IN ("
            "  SELECT user_id FROM line_user_bindings WHERE line_user_id = $2"
            ")",
            organization_id,
            line_user_id,
        )
        user_row = await cleanup.fetchrow(
            "SELECT user_id FROM line_user_bindings WHERE line_user_id = $1", line_user_id
        )
        await cleanup.execute(
            "DELETE FROM line_user_bindings WHERE line_user_id = $1", line_user_id
        )
        if user_row is not None:
            await cleanup.execute("DELETE FROM users WHERE id = $1", user_row["user_id"])
        await cleanup.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        await cleanup.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await cleanup.execute("COMMIT")
    finally:
        await cleanup.close()


async def _cleanup_volunteer(*, organization_id, user_id, line_user_id) -> None:
    cleanup = await asyncpg.connect(_database_url())
    try:
        await cleanup.execute("BEGIN")
        await cleanup.execute("DELETE FROM adoption_drafts WHERE adopter_user_id = $1", user_id)
        await cleanup.execute("DELETE FROM webhook_sessions WHERE user_id = $1", user_id)
        await cleanup.execute(
            "DELETE FROM line_user_bindings WHERE line_user_id = $1", line_user_id
        )
        await cleanup.execute(
            "DELETE FROM organization_memberships WHERE organization_id = $1", organization_id
        )
        await cleanup.execute("DELETE FROM users WHERE id = $1", user_id)
        await cleanup.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await cleanup.execute("COMMIT")
    finally:
        await cleanup.close()


def test_new_adopter_completes_specific_animal_flow_through_the_real_webhook_endpoint(
    monkeypatch,
) -> None:
    # This test used to rely on `_postback_event`'s missing replyToken to
    # avoid real outbound LINE calls — but Rich Menu switching (unlike
    # `_reply`) doesn't need a replyToken to fire, so a real channel token
    # here would make a real (and here, invalid-user) `link_rich_menu` call.
    # Force the mock adapter explicitly instead, like the other tests below.
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-specific-animal-flow")
    get_settings.cache_clear()

    organization_id = uuid4()
    animal_id = uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(_insert_adoption_fixtures(organization_id=organization_id, animal_id=animal_id))
    try:
        client = TestClient(app)

        response = _signed_post(
            client,
            [_postback_event(line_user_id, "action=start_adoption_matching&flow=adoption")],
        )
        assert response.status_code == 200
        assert response.json()["event_results"][0]["status"] == "processed"

        response = _signed_post(
            client,
            [
                _postback_event(
                    line_user_id,
                    f"action=select_organization&flow=adoption&value={organization_id}",
                )
            ],
        )
        assert response.json()["event_results"][0]["status"] == "processed"

        response = _signed_post(
            client,
            [
                _postback_event(
                    line_user_id, "action=choose_path&flow=adoption&value=specific_animal"
                )
            ],
        )
        assert response.json()["event_results"][0]["status"] == "processed"

        # Re-tapping the rich menu mid-conversation (organization and path
        # already chosen) must resume the existing draft, not error.
        response = _signed_post(
            client,
            [_postback_event(line_user_id, "action=start_adoption_matching&flow=adoption")],
        )
        assert response.json()["event_results"][0]["status"] == "processed", response.json()

        response = _signed_post(
            client,
            [
                _postback_event(
                    line_user_id,
                    f"action=select_target_animal&flow=adoption&value={animal_id}",
                )
            ],
        )
        assert response.json()["event_results"][0]["status"] == "processed"

        response = _signed_post(
            client,
            [_postback_event(line_user_id, "action=confirm_target_animal&flow=adoption")],
        )
        assert response.json()["event_results"][0]["status"] == "processed"

        for code in ("apartment_small", "first_time", "none", "adults_only", "work_from_home"):
            response = _signed_post(
                client,
                [_postback_event(line_user_id, f"action=answer&flow=adoption&value={code}")],
            )
            assert response.json()["event_results"][0]["status"] == "processed"

        response = _signed_post(client, [_text_event(line_user_id, "0911222333")])
        assert response.json()["event_results"][0]["status"] == "processed"

        response = _signed_post(
            client, [_postback_event(line_user_id, "action=submit&flow=adoption")]
        )
        assert response.json()["event_results"][0]["status"] == "processed"

        async def _verify() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                inquiry = await connection.fetchrow(
                    "SELECT * FROM adoption_inquiries WHERE organization_id = $1",
                    organization_id,
                )
                assert inquiry is not None
                assert inquiry["target_animal_id"] == animal_id
                assert inquiry["phone_number"] == "0911222333"
                assert inquiry["status"] == "new"
                draft = await connection.fetchrow(
                    "SELECT * FROM adoption_drafts WHERE organization_id = $1", organization_id
                )
                assert draft["status"] == "submitted"
            finally:
                await connection.close()

        asyncio.run(_verify())
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_existing_volunteer_postback_flow_is_unaffected_by_adoption_routing(monkeypatch) -> None:
    # Force the mock adapter so the volunteer Rich Menu self-heal sync
    # (added for the adoption-only default menu) doesn't make a real LINE
    # call for this test's fake line_user_id.
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-volunteer-unaffected")
    get_settings.cache_clear()

    organization_id, user_id, membership_id = uuid4(), uuid4(), uuid4()
    line_user_id = f"Uvol{uuid4().hex}"
    asyncio.run(
        _insert_volunteer_fixtures(
            organization_id=organization_id,
            user_id=user_id,
            membership_id=membership_id,
            line_user_id=line_user_id,
        )
    )
    try:
        client = TestClient(app)

        response = _signed_post(client, [_postback_event(line_user_id, "action=start_care_report")])

        assert response.status_code == 200
        assert response.json()["event_results"][0]["status"] == "processed", response.json()

        async def _verify_no_adoption_side_effect() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT id FROM adoption_drafts WHERE adopter_user_id = $1", user_id
                )
                assert draft is None
            finally:
                await connection.close()

        asyncio.run(_verify_no_adoption_side_effect())
    finally:
        asyncio.run(
            _cleanup_volunteer(
                organization_id=organization_id, user_id=user_id, line_user_id=line_user_id
            )
        )
        get_settings.cache_clear()


def test_adopter_can_cancel_from_every_step_not_just_review(monkeypatch) -> None:
    """Every adoption step must offer a way out — not only the final review
    screen — otherwise a user who changes their mind gets stuck.

    This test reads `debug_replies`, which only exists when the mock LINE
    adapter is in play. Force that regardless of whatever real credentials a
    developer's local `.env` may currently hold (e.g. while live-testing
    against a real LINE channel), so this check doesn't silently stop running.
    """
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-cancel-check")
    get_settings.cache_clear()

    def event_with_reply_token(data: str) -> dict:
        # Unlike `_postback_event`, this test wants `_reply()` to actually
        # invoke the (mock, so still network-free) adapter so its captured
        # `debug_replies` has something to inspect.
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    organization_id = uuid4()
    animal_id = uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(_insert_adoption_fixtures(organization_id=organization_id, animal_id=animal_id))
    try:
        client = TestClient(app)

        response = _signed_post(
            client,
            [event_with_reply_token("action=start_adoption_matching&flow=adoption")],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        quick_reply = next(m["quickReply"] for m in messages if m.get("quickReply"))
        assert any(
            item["action"]["data"] == "action=cancel&flow=adoption" for item in quick_reply["items"]
        ), "SELECTING_ORGANIZATION must offer a cancel option"

        response = _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_organization&flow=adoption&value={organization_id}",
                )
            ],
        )
        # CHOOSING_PATH's own options now live on the Rich Menu, not in-chat —
        # this text nudge only needs to offer a way out.
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        quick_reply = next(m["quickReply"] for m in messages if m.get("quickReply"))
        assert any(
            item["action"]["data"] == "action=cancel&flow=adoption" for item in quick_reply["items"]
        ), "CHOOSING_PATH must offer a cancel option"

        response = _signed_post(client, [event_with_reply_token("action=cancel&flow=adoption")])
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("已取消這次領養媒合對話" in m.get("text", "") for m in messages)
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_select_region_returns_shelter_flex_cards_without_mutating_draft_state(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-select-region")
    get_settings.cache_clear()

    def event_with_reply_token(data: str) -> dict:
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    organization_id = uuid4()
    animal_id = uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(
        _insert_adoption_fixtures(
            organization_id=organization_id, animal_id=animal_id, region="north"
        )
    )
    try:
        client = TestClient(app)
        _signed_post(
            client, [event_with_reply_token("action=start_adoption_matching&flow=adoption")]
        )

        response = _signed_post(
            client, [event_with_reply_token("action=select_region&flow=adoption&value=north")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        flex = next(m for m in messages if m.get("type") == "flex")
        button = flex["contents"]["body"]["contents"][-1]
        assert f"value={organization_id}" in button["action"]["data"]

        response = _signed_post(
            client, [event_with_reply_token("action=select_region&flow=adoption&value=south")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("目前沒有開放領養媒合的收容所" in m.get("text", "") for m in messages)

        async def _verify_state_unchanged() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT current_step FROM adoption_drafts WHERE organization_id IS NULL "
                    "AND adopter_user_id IN "
                    "(SELECT user_id FROM line_user_bindings WHERE line_user_id = $1)",
                    line_user_id,
                )
                assert draft["current_step"] == "selecting_organization"
            finally:
                await connection.close()

        asyncio.run(_verify_state_unchanged())
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_rich_menu_switches_across_adoption_flow_transitions(monkeypatch) -> None:
    """Region/path selection and cancellation each switch this adopter's
    personal Rich Menu — verified via the mock adapter's `linked_menus` log,
    since a real LINE user's linked menu isn't otherwise observable here."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-rich-menu-switch")
    monkeypatch.setenv("LINE_RICH_MENU_DEFAULT_ID", "richmenu-default")
    monkeypatch.setenv("LINE_RICH_MENU_REGION_SELECT_ID", "richmenu-region-select")
    monkeypatch.setenv("LINE_RICH_MENU_PATH_SELECT_ID", "richmenu-path-select")
    get_settings.cache_clear()

    def event_with_reply_token(data: str) -> dict:
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    organization_id = uuid4()
    animal_id = uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(_insert_adoption_fixtures(organization_id=organization_id, animal_id=animal_id))
    try:
        client = TestClient(app)

        response = _signed_post(
            client, [event_with_reply_token("action=start_adoption_matching&flow=adoption")]
        )
        assert response.json()["debug_linked_menus"] == [
            {"rich_menu_id": "richmenu-region-select", "user_id": line_user_id}
        ]

        response = _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_organization&flow=adoption&value={organization_id}"
                )
            ],
        )
        assert response.json()["debug_linked_menus"] == [
            {"rich_menu_id": "richmenu-path-select", "user_id": line_user_id}
        ]

        response = _signed_post(client, [event_with_reply_token("action=cancel&flow=adoption")])
        assert response.json()["debug_linked_menus"] == [
            {"rich_menu_id": "richmenu-default", "user_id": line_user_id}
        ]
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()
