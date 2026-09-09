from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from services.api.app.api import line_webhook
from services.api.app.api.errors import DomainError
from services.api.app.application.line_menu_actions import (
    BACK_TO_DEFAULT_MENU_ACTION,
    MENU_LIFF_ACTIONS,
    MENU_PLACEHOLDER_ACTIONS,
    STAFF_MENU_ACTIONS,
)
from services.api.app.application.line_rich_menu_routing import (
    MENU_ADOPTER,
    MENU_DEFAULT,
    MENU_STAFF,
    MENU_VOLUNTEER,
    LineRole,
    RichMenuRoutingService,
    build_registry,
    menu_key_for_role,
)
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter

# 這些 action 由 webhook 自行處理，不在 MENU_PLACEHOLDER_ACTIONS 裡。
WEBHOOK_HANDLED_ACTIONS = {
    "start_binding",
    "start_volunteer_application",
    "start_adoption_matching",
    "open_adoption_hub",
    "start_growth_diary",
    "walk_report",
    BACK_TO_DEFAULT_MENU_ACTION,
    *STAFF_MENU_ACTIONS,
}


def _postback_event(data: str, *, line_user_id: str | None = None) -> dict:
    event = {"type": "postback", "replyToken": "reply-1", "postback": {"data": data}}
    if line_user_id is not None:
        event["source"] = {"userId": line_user_id}
    return event


@pytest.mark.parametrize("text", ["開始散步回報", " 開始散步回報 "])
def test_walk_report_command_is_exact_with_whitespace_normalization(text: str) -> None:
    assert line_webhook._is_walk_report_command(
        {"type": "message", "message": {"type": "text", "text": text}}
    )


@pytest.mark.parametrize("text", ["開始照護回報", "開始散步回報！", "我想開始散步回報"])
def test_walk_report_command_rejects_legacy_and_near_matches(text: str) -> None:
    assert not line_webhook._is_walk_report_command(
        {"type": "message", "message": {"type": "text", "text": text}}
    )


def test_walk_report_context_failure_uses_volunteer_guidance() -> None:
    message = line_webhook._care_report_context_message()

    assert "服務收容所" in message["text"]
    assert "志工流程" in message["text"]
    assert "領養媒合" not in message["text"]


def test_walk_report_context_mapping_precedes_adopter_fallback() -> None:
    source = inspect.getsource(line_webhook.webhook)

    volunteer_mapping = source.index(
        'error.code == "shelter_context_required" and _is_walk_report_command(event)'
    )
    adopter_fallback = source.index("await _is_adopter_only_line_user(session, line_user_id)")
    assert volunteer_mapping < adopter_fallback


def test_walk_command_routing_precedes_active_adoption_free_text() -> None:
    source = inspect.getsource(line_webhook.webhook)

    assert source.index("_is_walk_report_command(event)") < source.index(
        "_active_adoption_draft(session, line_user_id)"
    )
    assert source.index('postback_values.get("flow"') < source.index("_handle_postback(")


def test_walk_report_menu_sync_follows_server_side_context_resolution() -> None:
    source = inspect.getsource(line_webhook._handle_walk_report_command)

    assert source.index("_resolve_context") < source.index("_switch_rich_menu")


@pytest.mark.asyncio
async def test_walk_report_postback_restores_volunteer_menu_after_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    switch_menu = AsyncMock(return_value=True)
    entry = AsyncMock(return_value={"type": "flex", "altText": "散步回報"})
    reply = AsyncMock()
    monkeypatch.setattr(line_webhook, "_switch_rich_menu", switch_menu)
    monkeypatch.setattr(line_webhook, "_walk_entry_bubble", entry)
    monkeypatch.setattr(line_webhook, "_reply", reply)

    await line_webhook._handle_postback(
        object(),
        object(),
        _postback_event("action=walk_report", line_user_id="U-controlled"),
        user_id=uuid4(),
        organization_id=uuid4(),
        membership_id=uuid4(),
        public_base_url="https://acceptance.example.net",
    )

    switch_menu.assert_awaited_once_with("U-controlled", LineRole.VOLUNTEER)
    reply.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_adoptable", [True, False])
async def test_walk_confirmation_uses_public_capability_for_active_animals(
    monkeypatch: pytest.MonkeyPatch, is_adoptable: bool
) -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        name="小森",
        shelter_number="A-001",
        status="active",
        is_adoptable=is_adoptable,
        current_photo_key="animals/a/primary.jpg",
    )
    candidate = SimpleNamespace(animal=animal, area=SimpleNamespace(name="北區 A3"))

    class Authentication:
        def __init__(self, session):
            assert session == "session"

        async def get_organization(self, scoped_organization_id):
            assert scoped_organization_id == organization_id
            return SimpleNamespace(name="浪浪森友會 A")

    class Photos:
        def __init__(self, session):
            assert session == "session"

        async def issue_url(self, **kwargs):
            assert kwargs == {
                "public_base_url": "https://strayhub.example",
                "organization_id": organization_id,
                "animal": animal,
                "purpose": line_webhook.VOLUNTEER_WALK_PHOTO,
            }
            return f"https://strayhub.example/v1/public/animals/{animal.id}/photo?token=safe"

    monkeypatch.setattr(line_webhook, "AuthenticationRepository", Authentication)
    monkeypatch.setattr(line_webhook, "ExternalAnimalPhotoService", Photos)

    bubble = await line_webhook._walk_confirmation_bubble(
        "session",
        organization_id,
        candidate,
        public_base_url="https://strayhub.example",
    )

    assert bubble["contents"]["hero"]["url"].startswith(
        f"https://strayhub.example/v1/public/animals/{animal.id}/photo"
    )


@pytest.mark.asyncio
async def test_walk_confirmation_photo_failure_keeps_confirmation_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        name="小森",
        shelter_number="A-001",
        status="active",
        is_adoptable=False,
        current_photo_key="animals/a/primary.jpg",
    )
    candidate = SimpleNamespace(animal=animal, area=SimpleNamespace(name="北區 A3"))

    class Authentication:
        def __init__(self, _session):
            pass

        async def get_organization(self, _organization_id):
            return SimpleNamespace(name="浪浪森友會 A")

    class Photos:
        def __init__(self, _session):
            pass

        async def issue_url(self, **_kwargs):
            raise RuntimeError("synthetic capability failure")

    monkeypatch.setattr(line_webhook, "AuthenticationRepository", Authentication)
    monkeypatch.setattr(line_webhook, "ExternalAnimalPhotoService", Photos)

    bubble = await line_webhook._walk_confirmation_bubble(
        "session",
        organization_id,
        candidate,
        public_base_url="https://strayhub.example",
    )

    assert "hero" not in bubble["contents"]
    actions = [
        item["action"]["data"]
        for item in bubble["contents"]["body"]["contents"]
        if "action" in item
    ]
    assert any("action=confirm_animal" in action for action in actions)
    assert "action=find_dog" in actions


@pytest.mark.asyncio
async def test_single_text_result_uses_shared_walk_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    candidate = SimpleNamespace(animal=SimpleNamespace(id=uuid4()))
    calls = []

    class Selection:
        async def search_page(self, **_kwargs):
            return SimpleNamespace(items=(candidate,), total=1)

    async def confirmation(session, scoped_organization_id, selected, *, public_base_url):
        calls.append((session, scoped_organization_id, selected, public_base_url))
        return {"type": "text", "text": "confirmation"}

    monkeypatch.setattr(line_webhook, "_selection_service", lambda *_args: Selection())
    monkeypatch.setattr(line_webhook, "_walk_confirmation_bubble", confirmation)

    result = await line_webhook._search_result_bubble(
        "session",
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        query="小森",
        page=1,
        public_base_url="https://strayhub.example",
    )

    assert result == {"type": "text", "text": "confirmation"}
    assert calls == [("session", organization_id, candidate, "https://strayhub.example")]


@pytest.mark.asyncio
async def test_select_animal_postback_uses_shared_walk_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(id=uuid4())
    candidate = SimpleNamespace(animal=animal)
    calls = []

    class Selection:
        async def confirm(self, **_kwargs):
            return candidate

    async def confirmation(session, scoped_organization_id, selected, *, public_base_url):
        calls.append((session, scoped_organization_id, selected, public_base_url))
        return {"type": "text", "text": "confirmation"}

    monkeypatch.setattr(line_webhook, "_selection_service", lambda *_args: Selection())
    monkeypatch.setattr(line_webhook, "_walk_confirmation_bubble", confirmation)
    line = MockLineAdapter()

    await line_webhook._handle_postback(
        "session",
        line,
        _postback_event(f"action=select_animal&animal_id={animal.id}"),
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        public_base_url="https://strayhub.example",
    )

    assert calls == [("session", organization_id, candidate, "https://strayhub.example")]
    assert line.replies[0][1] == [{"type": "text", "text": "confirmation"}]


def test_all_walk_confirmation_entry_paths_pass_public_base_url() -> None:
    source = inspect.getsource(line_webhook)
    assert source.count("_walk_confirmation_bubble(") >= 4
    assert source.count("public_base_url=public_base_url") >= 7
    walk_builder = inspect.getsource(line_webhook._walk_confirmation_bubble)
    assert "ExternalAnimalPhotoService" in walk_builder
    assert ".signed_url(" not in walk_builder


@pytest.mark.asyncio
@pytest.mark.parametrize("action", sorted(MENU_PLACEHOLDER_ACTIONS))
async def test_every_menu_action_gets_its_placeholder_reply(action: str) -> None:
    """選單項目全部要有回應；漏接的會掉進照護回報流程回「缺少回報草稿識別」。"""
    line = MockLineAdapter()

    handled = await line_webhook._handle_menu_action(line, _postback_event(f"action={action}"))

    assert handled is True
    assert line.replies[0][1][0]["text"] == MENU_PLACEHOLDER_ACTIONS[action]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", sorted(MENU_LIFF_ACTIONS))
async def test_staff_liff_action_waits_for_server_side_context(action: str) -> None:
    line = MockLineAdapter()

    handled = await line_webhook._handle_menu_action(line, _postback_event(f"action={action}"))

    assert handled is False
    assert line.replies == []


@pytest.mark.asyncio
async def test_staff_liff_action_requires_staff_role() -> None:
    line = MockLineAdapter()

    with pytest.raises(DomainError) as caught:
        await line_webhook._handle_staff_menu_action(
            None,
            line,
            _postback_event("action=staff_create_animal"),
            organization_id=uuid4(),
            role=LineRole.VOLUNTEER,
        )

    assert getattr(caught.value, "code", None) == "staff_access_required"
    assert line.replies == []


@pytest.mark.asyncio
async def test_staff_liff_action_uses_configured_liff_after_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        line_webhook,
        "get_settings",
        lambda: SimpleNamespace(line_staff_liff_id="staff-liff-id"),
    )
    line = MockLineAdapter()

    handled = await line_webhook._handle_staff_menu_action(
        None,
        line,
        _postback_event("action=staff_update_health"),
        organization_id=uuid4(),
        role=LineRole.SHELTER_ADMIN,
    )

    assert handled is True
    uri = line.replies[0][1][0]["quickReply"]["items"][0]["action"]["uri"]
    assert uri == ("https://liff.line.me/staff-liff-id?action=staff_update_health")


@pytest.mark.asyncio
async def test_staff_animal_list_is_scoped_after_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()

    class Repository:
        def __init__(self, session, scoped_organization_id):
            assert session == "session"
            assert scoped_organization_id == organization_id

        async def list_active(self):
            return [SimpleNamespace(name="小黑", shelter_number="A-1")]

    monkeypatch.setattr(line_webhook, "AnimalRepository", Repository)
    line = MockLineAdapter()

    handled = await line_webhook._handle_staff_menu_action(
        "session",
        line,
        _postback_event("action=staff_animal_list"),
        organization_id=organization_id,
        role=LineRole.STAFF,
    )

    assert handled is True
    assert "小黑（A-1）" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_back_to_default_menu_switches_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_switch(line_user_id: str | None) -> bool:
        assert line_user_id == "Uvolunteer0123456789"
        return True

    monkeypatch.setattr(line_webhook, "_switch_menu_to_default", fake_switch)
    line = MockLineAdapter()
    event = _postback_event("action=back_to_default_menu")
    event["source"] = {"userId": "Uvolunteer0123456789"}

    handled = await line_webhook._handle_menu_action(line, event)

    assert handled is True
    assert "已切回主選單" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_back_to_default_menu_reports_unavailable_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_switch(line_user_id: str | None) -> bool:
        return False

    monkeypatch.setattr(line_webhook, "_switch_menu_to_default", fake_switch)
    line = MockLineAdapter()
    event = _postback_event("action=back_to_default_menu")
    event["source"] = {"userId": "Uvolunteer0123456789"}

    handled = await line_webhook._handle_menu_action(line, event)

    assert handled is True
    assert "尚未啟用" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_start_binding_is_answered_without_membership() -> None:
    line = MockLineAdapter()

    handled = await line_webhook._handle_menu_action(line, _postback_event("action=start_binding"))

    assert handled is True
    assert "綁定" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_nonlocal_disabled_gate_rejects_new_menu_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DisabledSettings:
        @staticmethod
        def line_role_menu_features_active() -> bool:
            return False

    monkeypatch.setattr(line_webhook, "get_settings", lambda: DisabledSettings())
    line = MockLineAdapter()

    handled = await line_webhook._handle_menu_action(
        line, _postback_event("action=start_adoption_matching&flow=adoption")
    )

    assert handled is True
    assert line.replies[0][1][0]["text"] == "此 LINE 功能目前尚未開放。"


@pytest.mark.asyncio
async def test_care_report_postbacks_are_left_to_the_draft_handler() -> None:
    """草稿流程的 action 不可被選單處理器吃掉。"""
    line = MockLineAdapter()

    for data in ("action=answer&draft_token=t", "action=select_animal", "action=submit"):
        assert await line_webhook._handle_menu_action(line, _postback_event(data)) is False
    assert line.replies == []


@pytest.mark.asyncio
async def test_non_postback_events_are_ignored() -> None:
    line = MockLineAdapter()
    event = {"type": "message", "replyToken": "r", "message": {"type": "text", "text": "hi"}}

    assert await line_webhook._handle_menu_action(line, event) is False
    assert line.replies == []


@pytest.mark.parametrize(
    "path", sorted(Path("infra/local").glob("line-rich-menu-*.yaml")), ids=lambda p: p.stem
)
def test_every_configured_menu_action_has_a_handler(path: Path) -> None:
    """選單項目沒接處理者的話，postback 會掉進照護回報流程回「缺少回報草稿識別」。

    寫死清單會在改選單時失效，所以直接讀 yaml 比對。
    """
    import yaml

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in document["actions"]:
        action = item["data"].split("action=", 1)[1].split("&")[0]
        assert action in MENU_PLACEHOLDER_ACTIONS or action in WEBHOOK_HANDLED_ACTIONS, (
            f"{path.name} 的 {action} 沒有任何處理者"
        )


def test_default_menu_offers_volunteer_and_adoption_entries() -> None:
    """一進來就分成志工／領養兩條路；綁定不是獨立按鈕（報名時會隱含建立）。

    「領養流程」只是入口，不直接進領養對話——見
    test_adoption_hub_menu_offers_matching_and_growth_diary_entries。"""
    import yaml

    document = yaml.safe_load(
        Path("infra/local/line-rich-menu-default.yaml").read_text(encoding="utf-8")
    )
    actions = [item["data"].split("action=", 1)[1] for item in document["actions"]]

    assert actions == [
        "start_volunteer_application",
        "open_adoption_hub",
    ]


def test_adoption_hub_menu_offers_matching_and_growth_diary_entries() -> None:
    """預設選單的「領養流程」切到這張兩格選單——見 open_adoption_hub postback。"""
    import yaml

    document = yaml.safe_load(
        Path("infra/local/line-rich-menu-adoption-hub.yaml").read_text(encoding="utf-8")
    )
    actions = [item["data"].split("action=", 1)[1] for item in document["actions"]]

    assert actions == [
        "start_adoption_matching&flow=adoption",
        "start_growth_diary&flow=growth_diary",
    ]


@pytest.mark.parametrize(
    ("role", "selected", "expected"),
    [
        (None, False, MENU_DEFAULT),
        ("unknown", False, MENU_DEFAULT),
        (LineRole.VOLUNTEER, False, MENU_VOLUNTEER),
        (LineRole.ADOPTER, False, MENU_ADOPTER),
        (LineRole.STAFF, False, MENU_DEFAULT),
        (LineRole.STAFF, True, MENU_STAFF),
        (LineRole.SHELTER_ADMIN, True, MENU_STAFF),
        (LineRole.PLATFORM_ADMIN, False, MENU_DEFAULT),
        (LineRole.PLATFORM_ADMIN, True, MENU_DEFAULT),
    ],
)
def test_role_routing_requires_verified_shelter_context(
    role: str | None, selected: bool, expected: str
) -> None:
    assert menu_key_for_role(role, organization_selected=selected) == expected


def test_unbound_identity_always_uses_default_menu() -> None:
    assert (
        menu_key_for_role(LineRole.STAFF, bound=False, organization_selected=True) == MENU_DEFAULT
    )


@pytest.mark.asyncio
async def test_missing_role_menu_id_is_a_noop() -> None:
    line = MockLineAdapter()
    router = RichMenuRoutingService(line, build_registry(default="default-id"))

    linked = await router.link_for_user(
        line_user_id="U-staff",
        role=LineRole.STAFF,
        organization_selected=True,
    )

    assert linked is None


def test_all_missing_role_menu_ids_disable_router_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        line_rich_menu_default_id="",
        line_rich_menu_volunteer_id="",
        line_rich_menu_adopter_id="",
        line_rich_menu_staff_id="",
        line_role_menu_features_active=lambda: True,
    )
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)

    assert line_webhook._rich_menu_router() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["messaging_api_5xx", "messaging_api_timeout"])
async def test_menu_api_failure_is_best_effort_for_webhook(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    class FailingRouter:
        async def link_for_user(self, **kwargs):
            raise RuntimeError(failure)

    monkeypatch.setattr(line_webhook, "_rich_menu_router", lambda: FailingRouter())

    assert await line_webhook._switch_rich_menu("U-user", LineRole.VOLUNTEER) is False


def test_adoption_inquiry_submission_does_not_switch_to_adopter_menu() -> None:
    """沒有正式 adoption-completed lifecycle 前，送出 inquiry 不能改變角色選單。"""
    source = inspect.getsource(line_webhook._handle_adoption_postback)

    assert "LineRole.ADOPTER" not in source
    assert "_switch_rich_menu" not in source
