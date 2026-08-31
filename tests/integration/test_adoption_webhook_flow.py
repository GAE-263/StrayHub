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
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiAnimalRecommendation,
    GeminiClient,
    GeminiRankedRecommendation,
    GeminiSuitabilityResult,
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


async def _insert_two_animal_fixtures(
    *, organization_id, target_animal_id, other_animal_id
) -> None:
    """A shelter with two adoptable animals — `target_animal_id` has a known
    shelter_number (for the free-text search test) and a profile engineered
    to score 0% against a poorly-matched preference set (large/high-energy,
    no compatible temperament tags), so the low-score suggestion path fires
    and `other_animal_id` is available as the one alternative to suggest."""
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Two Animal Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"TWOANI-{organization_id.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, is_adoptable, size,
                 energy, temperament, created_at, updated_at)
            VALUES ($1, $2, '大寶', 'A100', 'active', true, 'large', 'high', '[]'::jsonb,
                    now(), now())
            """,
            target_animal_id,
            organization_id,
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, is_adoptable, size,
                 energy, temperament, created_at, updated_at)
            VALUES ($1, $2, '小寶', 'B200', 'active', true, 'small', 'low', '[]'::jsonb,
                    now(), now())
            """,
            other_animal_id,
            organization_id,
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


def _flex_texts(message: dict) -> list[str]:
    """All "text" leaf values anywhere in a Flex message's contents tree —
    lets assertions check a card's copy without knowing its exact structure."""
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


def _capture_pushes(monkeypatch) -> list[tuple[str, list[dict]]]:
    """The webhook constructs a fresh `MockLineAdapter()` per request (see
    `webhook()`), so there's no instance to inspect from outside once the
    request finishes — the AI background task's pushes are the only effect
    of a request that ISN'T reflected in `debug_replies` (background tasks
    run strictly after the response body is already built). Patch the class
    method itself to also record every call, across however many instances
    get created during the test."""
    calls: list[tuple[str, list[dict]]] = []
    original_push = MockLineAdapter.push

    async def recording_push(self, *, to_user_id: str, messages: list[dict]) -> None:
        calls.append((to_user_id, messages))
        await original_push(self, to_user_id=to_user_id, messages=messages)

    monkeypatch.setattr(MockLineAdapter, "push", recording_push)
    return calls


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
    # No Gemini credential here — the AI step degrades to its fallback
    # (see test_ai_suitability_analysis_degrades_gracefully_without_credentials
    # for that behavior in detail), still unblocking this end-to-end flow.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_SERVICE_ACCOUNT_PATH", "")
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

        for code in (
            "apartment_small",
            "first_time",
            "none",
            "adults_only",
            "work_from_home",
            "structured",
            "high_patience",
            "companionship",
        ):
            response = _signed_post(
                client,
                [_postback_event(line_user_id, f"action=answer&flow=adoption&value={code}")],
            )
            assert response.json()["event_results"][0]["status"] == "processed"

        response = _signed_post(
            client, [_postback_event(line_user_id, "action=confirm_answers&flow=adoption")]
        )
        assert response.json()["event_results"][0]["status"] == "processed"

        # No Gemini credential configured (see monkeypatch above) — the AI
        # background task degrades to its fallback and moves the draft
        # straight into the name → contact time → phone number sequence.
        response = _signed_post(client, [_text_event(line_user_id, "王小明")])
        assert response.json()["event_results"][0]["status"] == "processed"

        response = _signed_post(client, [_text_event(line_user_id, "平日白天")])
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
                assert inquiry["adopter_name"] == "王小明"
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
        # The cancel confirmation is now a build_info_card Flex bubble, not a
        # plain text message — its altText mirrors the header title.
        assert any("已取消這次領養媒合對話" in m.get("altText", "") for m in messages)
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
        # "north" is a real region other local shelter data may also use
        # (see the demo/seed data note), so the carousel can legitimately
        # carry more than just this fixture's own bubble — find this
        # fixture's card by its own organization_id rather than assuming
        # it's the only (and therefore last) one.
        bubbles = (
            flex["contents"]["contents"]
            if flex["contents"]["type"] == "carousel"
            else [flex["contents"]]
        )
        matching_button = next(
            button
            for bubble in bubbles
            for button in bubble["body"]["contents"]
            if f"value={organization_id}" in button.get("action", {}).get("data", "")
        )
        assert f"value={organization_id}" in matching_button["action"]["data"]

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


def test_questionnaire_renders_as_flex_question_card_with_progress(monkeypatch) -> None:
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-question-card")
    get_settings.cache_clear()

    def event_with_reply_token(data: str) -> dict:
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    organization_id = uuid4()
    animal_id = uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(_insert_adoption_fixtures(organization_id=organization_id, animal_id=animal_id))
    try:
        client = TestClient(app)
        _signed_post(
            client, [event_with_reply_token("action=start_adoption_matching&flow=adoption")]
        )
        _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_organization&flow=adoption&value={organization_id}"
                )
            ],
        )
        _signed_post(
            client,
            [event_with_reply_token("action=choose_path&flow=adoption&value=specific_animal")],
        )
        _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_target_animal&flow=adoption&value={animal_id}"
                )
            ],
        )
        response = _signed_post(
            client, [event_with_reply_token("action=confirm_target_animal&flow=adoption")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        question_card = next(m for m in messages if m.get("type") == "flex")
        assert question_card["altText"] == "你家是什麼樣子呢？🏠"
        header_texts = _flex_texts({"contents": question_card["contents"]["header"]})
        assert any("1 / 8" in text for text in header_texts)
        progress = question_card["contents"]["header"]["contents"][-1]
        assert progress["contents"][0]["flex"] == 1
        assert progress["contents"][1]["flex"] == 7
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_confirming_answers_summary_lets_adopter_reconfirm_or_edit(monkeypatch) -> None:
    """Finishing the questionnaire must pause on a reconfirm-your-answers
    summary before anything else happens — "修改" returns to the last
    question (letting them page further back via each question's own
    "上一步"), and "確認無誤，繼續" is what actually moves the flow on."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-confirming-answers")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_SERVICE_ACCOUNT_PATH", "")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    def event_with_reply_token(data: str) -> dict:
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    organization_id = uuid4()
    animal_id = uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(_insert_adoption_fixtures(organization_id=organization_id, animal_id=animal_id))
    try:
        client = TestClient(app)
        _signed_post(
            client, [event_with_reply_token("action=start_adoption_matching&flow=adoption")]
        )
        _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_organization&flow=adoption&value={organization_id}"
                )
            ],
        )
        _signed_post(
            client,
            [event_with_reply_token("action=choose_path&flow=adoption&value=specific_animal")],
        )
        _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_target_animal&flow=adoption&value={animal_id}"
                )
            ],
        )
        _signed_post(client, [event_with_reply_token("action=confirm_target_animal&flow=adoption")])
        response = None
        for code in (
            "apartment_small",
            "first_time",
            "none",
            "adults_only",
            "work_from_home",
            "structured",
            "high_patience",
            "companionship",
        ):
            response = _signed_post(
                client, [event_with_reply_token(f"action=answer&flow=adoption&value={code}")]
            )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        summary_card = next(m for m in messages if m.get("type") == "flex")
        summary_texts = _flex_texts(summary_card)
        # Each Q&A row renders label and value as separate text nodes.
        assert any("居住環境" in text for text in summary_texts)
        assert any("小坪數公寓" in text for text in summary_texts)
        assert any("領養動機" in text for text in summary_texts)

        # "修改" goes back to the last question, not straight into a phone
        # number ask — and that question is blank again, ready to redo.
        response = _signed_post(client, [event_with_reply_token("action=back&flow=adoption")])
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        question_card = next(m for m in messages if m.get("type") == "flex")
        assert question_card["altText"] == "這次想領養毛孩，最主要是為了？💭"

        # Re-answer it, then actually confirm — only now does AI/contact-info
        # territory begin (covered by the AI-specific tests).
        response = _signed_post(
            client,
            [event_with_reply_token("action=answer&flow=adoption&value=companionship")],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any(m.get("type") == "flex" for m in messages)  # back to the summary

        _signed_post(client, [event_with_reply_token("action=confirm_answers&flow=adoption")])
        assert len(pushes) == 1
        _, pushed_messages = pushes[0]
        plain_texts = [m.get("text", "") for m in pushed_messages if m.get("type") == "text"]
        assert any("AI 適配度分析暫時無法使用" in text for text in plain_texts)

        async def _verify_state() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT current_step FROM adoption_drafts WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["current_step"] == "awaiting_adopter_name"
            finally:
                await connection.close()

        asyncio.run(_verify_state())
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_specific_animal_search_by_shelter_number_and_confirm_answers_starts_ai_analysis(
    monkeypatch,
) -> None:
    """The 心有所屬 path accepts a free-text shelter-number search alongside
    the quick-pick photo carousel; finishing the questionnaire and tapping
    confirm_answers must go straight into the "AI 正在分析適配度" wait card —
    the rule-based score is deliberately not shown here any more (it read as
    a confusing "0% 合拍度" right before the real AI card arrives)."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-shelter-number-search")
    # No Gemini credential — the AI background task degrades to its fallback
    # once BackgroundTasks run (see the AI-specific tests for that in detail);
    # this test is about the synchronous reply and the free-text search.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_SERVICE_ACCOUNT_PATH", "")
    get_settings.cache_clear()

    def event_with_reply_token(data: str) -> dict:
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    def text_with_reply_token(text: str) -> dict:
        return {**_text_event(line_user_id, text), "replyToken": uuid4().hex}

    organization_id = uuid4()
    target_animal_id, other_animal_id = uuid4(), uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(
        _insert_two_animal_fixtures(
            organization_id=organization_id,
            target_animal_id=target_animal_id,
            other_animal_id=other_animal_id,
        )
    )
    try:
        client = TestClient(app)
        _signed_post(
            client, [event_with_reply_token("action=start_adoption_matching&flow=adoption")]
        )
        _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_organization&flow=adoption&value={organization_id}"
                )
            ],
        )
        _signed_post(
            client,
            [event_with_reply_token("action=choose_path&flow=adoption&value=specific_animal")],
        )

        # Free-text shelter-number search, instead of tapping the carousel.
        response = _signed_post(client, [text_with_reply_token("A100")])
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        confirm_card = next(m for m in messages if m.get("type") == "flex")
        assert "大寶" in "".join(_flex_texts(confirm_card))

        _signed_post(client, [event_with_reply_token("action=confirm_target_animal&flow=adoption")])

        for code in (
            "house",
            "first_time",
            "none",
            "adults_only",
            "full_time_work",
            "structured",
            "high_patience",
            "companionship",
        ):
            response = _signed_post(
                client,
                [event_with_reply_token(f"action=answer&flow=adoption&value={code}")],
            )

        response = _signed_post(
            client, [event_with_reply_token("action=confirm_answers&flow=adoption")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        flex_messages = [m for m in messages if m.get("type") == "flex"]
        all_texts = [text for message in flex_messages for text in _flex_texts(message)]
        assert not any("合拍度" in text for text in all_texts), "no rule score should show here"
        assert any("AI 正在分析適配度" in text for text in all_texts)

        # No Gemini credential — the background task (already run by now, see
        # module docstring on BackgroundTasks/TestClient) degrades straight
        # to name → contact time → phone number, target animal unchanged.
        async def _verify_target_animal_unchanged_and_moved_on() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT target_animal_id, current_step FROM adoption_drafts "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["target_animal_id"] == target_animal_id
                assert draft["current_step"] == "awaiting_adopter_name"
            finally:
                await connection.close()

        asyncio.run(_verify_target_animal_unchanged_and_moved_on())
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def _drive_specific_animal_flow_through_confirm_answers(
    client: TestClient, *, line_user_id: str, organization_id, target_animal_id
) -> None:
    """Drives through CONFIRMING_ANSWERS and taps confirm_answers — which,
    since BackgroundTasks resolve synchronously within the same TestClient
    call, also means the AI analysis (or its no-credentials fallback) has
    already fully run and pushed by the time this returns."""

    def event_with_reply_token(data: str) -> dict:
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    _signed_post(client, [event_with_reply_token("action=start_adoption_matching&flow=adoption")])
    _signed_post(
        client,
        [
            event_with_reply_token(
                f"action=select_organization&flow=adoption&value={organization_id}"
            )
        ],
    )
    _signed_post(
        client,
        [event_with_reply_token("action=choose_path&flow=adoption&value=specific_animal")],
    )
    _signed_post(
        client,
        [
            event_with_reply_token(
                f"action=select_target_animal&flow=adoption&value={target_animal_id}"
            )
        ],
    )
    _signed_post(client, [event_with_reply_token("action=confirm_target_animal&flow=adoption")])
    for code in (
        "house",
        "first_time",
        "none",
        "adults_only",
        "full_time_work",
        "structured",
        "high_patience",
        "companionship",
    ):
        _signed_post(client, [event_with_reply_token(f"action=answer&flow=adoption&value={code}")])
    _signed_post(client, [event_with_reply_token("action=confirm_answers&flow=adoption")])


def test_ai_suitability_analysis_pushes_score_card_and_low_score_followup(monkeypatch) -> None:
    """Entering AWAITING_PHONE_NUMBER on the 心有所屬 path schedules a
    background AI suitability analysis (FastAPI BackgroundTasks — runs after
    the synchronous reply, so it's already done by the time `_signed_post`
    returns since TestClient drives the whole ASGI lifecycle in one call).
    A score under 60 must push the score card AND a free-text follow-up
    question in the same push, and mark the draft as awaiting that answer;
    the adopter's subsequent free-text answer then triggers the second
    Gemini call, whose result replaces the marker with nothing (cleared)."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-ai-suitability")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    async def fake_analyze_suitability(self, prompt: str) -> GeminiSuitabilityResult:
        return GeminiSuitabilityResult(score=35, explanation="活動力較高，跟目前作息可能需要磨合。")

    monkeypatch.setattr(GeminiClient, "analyze_suitability", fake_analyze_suitability)

    organization_id = uuid4()
    target_animal_id, other_animal_id = uuid4(), uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(
        _insert_two_animal_fixtures(
            organization_id=organization_id,
            target_animal_id=target_animal_id,
            other_animal_id=other_animal_id,
        )
    )
    try:
        client = TestClient(app)
        _drive_specific_animal_flow_through_confirm_answers(
            client,
            line_user_id=line_user_id,
            organization_id=organization_id,
            target_animal_id=target_animal_id,
        )

        assert len(pushes) == 1
        pushed_user_id, pushed_messages = pushes[0]
        assert pushed_user_id == line_user_id
        all_texts = [text for message in pushed_messages for text in _flex_texts(message)]
        plain_texts = [m.get("text", "") for m in pushed_messages if m.get("type") == "text"]
        assert any("35%" in text for text in all_texts)
        assert any("活動力較高" in text for text in all_texts)
        assert any("特殊需求" in text for text in plain_texts)

        async def _verify_draft_after_analysis() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT ai_suitability_score, ai_suitability_explanation, "
                    "ai_followup_target_animal_id FROM adoption_drafts "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["ai_suitability_score"] == 35
                assert "活動力較高" in draft["ai_suitability_explanation"]
                assert draft["ai_followup_target_animal_id"] == target_animal_id
            finally:
                await connection.close()

        asyncio.run(_verify_draft_after_analysis())

        async def fake_recommend_alternatives(
            self, prompt: str, *, valid_animal_ids: set[str]
        ) -> list[GeminiAnimalRecommendation]:
            assert str(other_animal_id) in valid_animal_ids
            return [
                GeminiAnimalRecommendation(animal_id=str(other_animal_id), reason="個性穩定安靜")
            ]

        monkeypatch.setattr(GeminiClient, "recommend_alternatives", fake_recommend_alternatives)

        response = _signed_post(
            client,
            [
                {
                    **_text_event(line_user_id, "想要個性安靜的女生"),
                    "replyToken": uuid4().hex,
                }
            ],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("謝謝告訴我們" in m.get("text", "") for m in messages)

        assert len(pushes) == 2
        _, alternatives_messages = pushes[1]
        alt_texts = [text for message in alternatives_messages for text in _flex_texts(message)]
        # The originally-chosen animal is offered back too (as "維持這隻"),
        # alongside the AI-picked alternative — the adopter must explicitly
        # (re)confirm a target before contact info is asked.
        assert any("大寶" in text for text in alt_texts)
        assert any("你原本選定的毛孩" in text for text in alt_texts)
        assert any("小寶" in text for text in alt_texts)
        assert any("個性穩定安靜" in text for text in alt_texts)

        async def _verify_marker_cleared_and_awaiting_selection() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT current_step, ai_followup_target_animal_id, candidate_match_ids "
                    "FROM adoption_drafts WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["ai_followup_target_animal_id"] is None
                assert draft["current_step"] == "selecting_alternative_animal"
                assert set(json.loads(draft["candidate_match_ids"])) == {
                    str(target_animal_id),
                    str(other_animal_id),
                }
            finally:
                await connection.close()

        asyncio.run(_verify_marker_cleared_and_awaiting_selection())

        # Confirming the alternative (not the original) must switch the
        # draft's target and require a fresh confirm before contact info.
        response = _signed_post(
            client,
            [
                {
                    **_postback_event(
                        line_user_id,
                        f"action=select_alternative_animal&flow=adoption&value={other_animal_id}",
                    ),
                    "replyToken": uuid4().hex,
                }
            ],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        confirm_card = next(m for m in messages if m.get("type") == "flex")
        assert "小寶" in "".join(_flex_texts(confirm_card))

        response = _signed_post(
            client,
            [
                {
                    **_postback_event(
                        line_user_id, "action=confirm_alternative_animal&flow=adoption"
                    ),
                    "replyToken": uuid4().hex,
                }
            ],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("請留下您的姓名" in str(m) for m in messages)

        async def _verify_target_switched_to_alternative() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT target_animal_id, current_step FROM adoption_drafts "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["target_animal_id"] == other_animal_id
                assert draft["current_step"] == "awaiting_adopter_name"
            finally:
                await connection.close()

        asyncio.run(_verify_target_switched_to_alternative())
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_ai_suitability_analysis_high_score_skips_straight_to_contact_card(monkeypatch) -> None:
    """A score of 60 or above needs no follow-up question — the same push
    that shows the AI card also moves the draft to AWAITING_PHONE_NUMBER and
    shows the contact-info card, with nothing else needed from the adopter."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-ai-high-score")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    async def fake_analyze_suitability(self, prompt: str) -> GeminiSuitabilityResult:
        return GeminiSuitabilityResult(score=82, explanation="非常合適的一組！")

    monkeypatch.setattr(GeminiClient, "analyze_suitability", fake_analyze_suitability)

    organization_id = uuid4()
    target_animal_id, other_animal_id = uuid4(), uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(
        _insert_two_animal_fixtures(
            organization_id=organization_id,
            target_animal_id=target_animal_id,
            other_animal_id=other_animal_id,
        )
    )
    try:
        client = TestClient(app)
        _drive_specific_animal_flow_through_confirm_answers(
            client,
            line_user_id=line_user_id,
            organization_id=organization_id,
            target_animal_id=target_animal_id,
        )

        assert len(pushes) == 1
        _, pushed_messages = pushes[0]
        all_texts = [text for message in pushed_messages for text in _flex_texts(message)]
        assert any("82%" in text for text in all_texts)
        assert any("非常合適" in text for text in all_texts)
        plain_texts = [m.get("text", "") for m in pushed_messages if m.get("type") == "text"]
        assert not any("特殊需求" in text for text in plain_texts)
        assert any(m.get("type") == "flex" and "請留下您的姓名" in str(m) for m in pushed_messages)

        async def _verify_draft_moved_straight_to_adopter_name() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT current_step, ai_suitability_score, ai_followup_target_animal_id "
                    "FROM adoption_drafts WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["current_step"] == "awaiting_adopter_name"
                assert draft["ai_suitability_score"] == 82
                assert draft["ai_followup_target_animal_id"] is None
            finally:
                await connection.close()

        asyncio.run(_verify_draft_moved_straight_to_adopter_name())

        # And the adopter can now actually give name → contact time → phone.
        _signed_post(
            client,
            [{**_text_event(line_user_id, "王小明"), "replyToken": uuid4().hex}],
        )
        _signed_post(
            client,
            [{**_text_event(line_user_id, "平日白天"), "replyToken": uuid4().hex}],
        )
        response = _signed_post(
            client,
            [{**_text_event(line_user_id, "0912345678"), "replyToken": uuid4().hex}],
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("領養意願摘要" in str(m) for m in messages)
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_ai_suitability_analysis_degrades_gracefully_without_credentials(monkeypatch) -> None:
    """Without either Gemini credential configured, the adopter must not be
    stuck waiting forever for an analysis that will never come — the
    background task still pushes a fallback message and moves the draft on
    to AWAITING_ADOPTER_NAME itself."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-ai-no-key")
    # A real credential may be configured locally in .env — an OS-level
    # delenv wouldn't unset it (pydantic-settings still reads unset-in-
    # os.environ vars straight from the .env file), so this test is
    # specifically about the "neither credential resolves to a truthy
    # value" case: explicit empty-string overrides beat the .env file.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_SERVICE_ACCOUNT_PATH", "")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    organization_id = uuid4()
    target_animal_id, other_animal_id = uuid4(), uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(
        _insert_two_animal_fixtures(
            organization_id=organization_id,
            target_animal_id=target_animal_id,
            other_animal_id=other_animal_id,
        )
    )
    try:
        client = TestClient(app)
        _drive_specific_animal_flow_through_confirm_answers(
            client,
            line_user_id=line_user_id,
            organization_id=organization_id,
            target_animal_id=target_animal_id,
        )

        assert len(pushes) == 1
        _, pushed_messages = pushes[0]
        plain_texts = [m.get("text", "") for m in pushed_messages if m.get("type") == "text"]
        assert any("AI 適配度分析暫時無法使用" in text for text in plain_texts)
        assert any(m.get("type") == "flex" for m in pushed_messages), "contact card must still show"

        async def _verify_draft_still_moved_on() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT current_step, ai_suitability_score, ai_followup_target_animal_id "
                    "FROM adoption_drafts WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["current_step"] == "awaiting_adopter_name"
                assert draft["ai_suitability_score"] is None
                assert draft["ai_followup_target_animal_id"] is None
            finally:
                await connection.close()

        asyncio.run(_verify_draft_still_moved_on())
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_recommend_me_ai_curation_pushes_ranked_recommendation_list(monkeypatch) -> None:
    """推薦名單路徑：問卷答完後，規則式先篩出候選池（AWAITING_AI_RECOMMENDATIONS），
    AI 背景任務重新評分排序後才 push 出最終名單，直接落在 SELECTING_MATCHED_ANIMAL —
    push 的分數/說明必須是 AI 給的，不是規則式的原始分數。"""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-recommend-me-ai")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    async def fake_rank_recommendations(
        self, prompt: str, *, valid_animal_ids: set[str]
    ) -> list[GeminiRankedRecommendation]:
        assert valid_animal_ids == {str(target_animal_id), str(other_animal_id)}
        return [
            GeminiRankedRecommendation(
                animal_id=str(other_animal_id),
                score=88,
                explanation="個性文靜，很適合你描述的生活步調。",
            ),
            GeminiRankedRecommendation(
                animal_id=str(target_animal_id),
                score=40,
                explanation="活動力偏高，可能需要多花心力磨合。",
            ),
        ]

    monkeypatch.setattr(GeminiClient, "rank_recommendations", fake_rank_recommendations)

    def event_with_reply_token(data: str) -> dict:
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    organization_id = uuid4()
    target_animal_id, other_animal_id = uuid4(), uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(
        _insert_two_animal_fixtures(
            organization_id=organization_id,
            target_animal_id=target_animal_id,
            other_animal_id=other_animal_id,
        )
    )
    try:
        client = TestClient(app)
        _signed_post(
            client, [event_with_reply_token("action=start_adoption_matching&flow=adoption")]
        )
        _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_organization&flow=adoption&value={organization_id}"
                )
            ],
        )
        _signed_post(
            client, [event_with_reply_token("action=choose_path&flow=adoption&value=recommend_me")]
        )
        for code in (
            "house",
            "experienced",
            "has_cats",
            "adults_only",
            "retired",
            "structured",
            "high_patience",
            "companionship",
            "small",
            "low",
        ):
            _signed_post(
                client, [event_with_reply_token(f"action=answer&flow=adoption&value={code}")]
            )

        assert len(pushes) == 1
        pushed_user_id, pushed_messages = pushes[0]
        assert pushed_user_id == line_user_id
        all_texts = [text for message in pushed_messages for text in _flex_texts(message)]
        assert any("小寶" in text for text in all_texts)
        assert any("88%" in text for text in all_texts)
        assert any("個性文靜" in text for text in all_texts)
        # The AI reranked the pool (小寶 first) — not the raw rule-based order.
        assert any("第 1 名推薦" in text for text in all_texts)

        async def _verify_curated_state() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT current_step, candidate_match_ids FROM adoption_drafts "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["current_step"] == "selecting_matched_animal"
                assert json.loads(draft["candidate_match_ids"]) == [
                    str(other_animal_id),
                    str(target_animal_id),
                ]
            finally:
                await connection.close()

        asyncio.run(_verify_curated_state())

        # Confirming the AI's top pick must land on the same name → contact
        # time → phone number sequence as 心有所屬, with no duplicate score
        # card shown again (the AI-curated list already served that purpose).
        _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_matched_animal&flow=adoption&value={other_animal_id}"
                )
            ],
        )
        response = _signed_post(
            client, [event_with_reply_token("action=confirm_target_animal&flow=adoption")]
        )
        messages = [m for batch in response.json()["debug_replies"] for m in batch]
        assert any("請留下您的姓名" in str(m) for m in messages)

        async def _verify_target_confirmed() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT target_animal_id, current_step FROM adoption_drafts "
                    "WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["target_animal_id"] == other_animal_id
                assert draft["current_step"] == "awaiting_adopter_name"
            finally:
                await connection.close()

        asyncio.run(_verify_target_confirmed())
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()


def test_recommend_me_ai_curation_degrades_to_rule_based_pool_without_credentials(
    monkeypatch,
) -> None:
    """No Gemini credentials — the recommendation list must still show up
    (unscored, rule-based order) rather than leaving the adopter stuck at
    AWAITING_AI_RECOMMENDATIONS forever."""
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "fake-test-recommend-me-ai-fallback")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_SERVICE_ACCOUNT_PATH", "")
    get_settings.cache_clear()
    pushes = _capture_pushes(monkeypatch)

    def event_with_reply_token(data: str) -> dict:
        return {**_postback_event(line_user_id, data), "replyToken": uuid4().hex}

    organization_id = uuid4()
    target_animal_id, other_animal_id = uuid4(), uuid4()
    line_user_id = f"Uadopt{uuid4().hex}"
    asyncio.run(
        _insert_two_animal_fixtures(
            organization_id=organization_id,
            target_animal_id=target_animal_id,
            other_animal_id=other_animal_id,
        )
    )
    try:
        client = TestClient(app)
        _signed_post(
            client, [event_with_reply_token("action=start_adoption_matching&flow=adoption")]
        )
        _signed_post(
            client,
            [
                event_with_reply_token(
                    f"action=select_organization&flow=adoption&value={organization_id}"
                )
            ],
        )
        _signed_post(
            client, [event_with_reply_token("action=choose_path&flow=adoption&value=recommend_me")]
        )
        for code in (
            "house",
            "experienced",
            "has_cats",
            "adults_only",
            "retired",
            "structured",
            "high_patience",
            "companionship",
            "small",
            "low",
        ):
            _signed_post(
                client, [event_with_reply_token(f"action=answer&flow=adoption&value={code}")]
            )

        assert len(pushes) == 1
        _, pushed_messages = pushes[0]
        all_texts = [text for message in pushed_messages for text in _flex_texts(message)]
        assert any("小寶" in text or "大寶" in text for text in all_texts)
        assert not any("%" in text for text in all_texts), "no rule score should render as a %"

        async def _verify_fallback_state() -> None:
            connection = await asyncpg.connect(_database_url())
            try:
                draft = await connection.fetchrow(
                    "SELECT current_step FROM adoption_drafts WHERE organization_id = $1",
                    organization_id,
                )
                assert draft["current_step"] == "selecting_matched_animal"
            finally:
                await connection.close()

        asyncio.run(_verify_fallback_state())
    finally:
        asyncio.run(_cleanup_adoption(organization_id=organization_id, line_user_id=line_user_id))
        get_settings.cache_clear()
