import pytest
from services.api.app.application.effective_observation_service import EffectiveOption
from services.api.app.application.line_message_presenter import (
    INK,
    animal_confirmation_bubble,
    daily_care_bubble,
    question_bubble,
)


def _option_actions(bubble: dict) -> list[dict]:
    return [
        content["action"]
        for content in bubble["contents"]["body"]["contents"]
        if "action" in content
    ]


def _texts(node) -> list[str]:
    """Every text value in a Flex subtree, so assertions survive layout changes."""
    if isinstance(node, dict):
        found = [node["text"]] if node.get("type") == "text" else []
        for value in node.values():
            found.extend(_texts(value))
        return found
    if isinstance(node, list):
        return [text for item in node for text in _texts(item)]
    return []


def test_question_bubble_uses_stable_code_in_postback() -> None:
    options = [EffectiveOption(f"activity.{index}", f"選項 {index}") for index in range(8)]

    bubble = question_bubble(
        options, draft_token="opaque", step="activity", title="精神體力", position=2, total=6
    )
    actions = _option_actions(bubble)

    assert "value=activity.0" in actions[0]["data"]
    assert actions[0]["label"] == "選項 0"


def test_question_bubble_offers_every_option() -> None:
    options = [EffectiveOption(f"gait.{index}", f"選項 {index}") for index in range(12)]

    bubble = question_bubble(
        options, draft_token="opaque", step="gait", title="走路姿勢", position=3, total=6
    )
    actions = _option_actions(bubble)

    assert sum(1 for action in actions if "action=answer" in action["data"]) == 12
    # 每題都額外提供一顆「今天沒觀察到這項」，不算在選項清單裡但要存在。
    assert any("action=skip_question" in action["data"] for action in actions)


def test_question_bubble_states_which_question_is_being_asked() -> None:
    bubble = question_bubble(
        [EffectiveOption("defecation.normal", "正常")],
        draft_token="opaque",
        step="defecation",
        title="大便",
        position=4,
        total=6,
    )

    header_texts = _texts(bubble["contents"]["header"])
    assert "大便" in header_texts
    assert any("4" in text and "6" in text for text in header_texts)
    assert "大便" in bubble["altText"]


def test_question_and_daily_progress_bars_use_visible_ink_fill() -> None:
    question = question_bubble(
        [EffectiveOption("activity.normal", "正常")],
        draft_token="opaque",
        step="activity",
        title="精神體力",
        position=3,
        total=6,
    )
    daily = daily_care_bubble(
        [("小森／A-001", "action=select_animal&animal_id=a", "今天尚未回報", False)],
        done=1,
        total=4,
        shown_through=1,
        more_data="action=today_overview&page=2",
    )

    for bubble, expected_width in ((question, "50%"), (daily, "25%")):
        progress = bubble["contents"]["header"]["contents"][-1]
        fill = progress["contents"][0]
        assert fill["backgroundColor"] == INK
        assert fill["width"] == expected_width


def test_question_bubble_without_options_explains_instead_of_showing_nothing() -> None:
    bubble = question_bubble(
        [], draft_token="opaque", step="appearance", title="身體外觀", position=6, total=6
    )

    assert _option_actions(bubble) == []
    assert bubble["contents"]["body"]["contents"][0]["text"]


def test_confirmation_shows_full_identity_photo_and_both_actions() -> None:
    bubble = animal_confirmation_bubble(
        animal_name="小森",
        shelter_number="A-001",
        area_label="北區 A3",
        organization_name="浪浪森友會 A",
        photo_url="https://example.test/photo.jpg",
        confirm_data="action=confirm_animal&animal_id=animal-a",
    )

    texts = _texts(bubble)
    assert {"A-001", "北區 A3", "浪浪森友會 A", "確認是這隻", "重新選擇"} <= set(texts)
    assert any("小森" in text for text in texts)
    assert bubble["contents"]["hero"]["url"] == "https://example.test/photo.jpg"
    assert bubble["contents"]["hero"]["aspectMode"] == "fit"


@pytest.mark.parametrize(
    "photo_url",
    [
        None,
        "http://strayhub.example/photo.jpg",
        "https://localhost/photo.jpg",
        "https://127.0.0.1/photo.jpg",
        "https://minio:9000/photo.jpg",
        "https://10.0.0.1/photo.jpg",
        "https://storage.googleapis.com/private-bucket/photo.jpg",
        "https://private-bucket.storage.googleapis.com/photo.jpg",
        "not-a-url",
    ],
)
def test_confirmation_omits_unsafe_photo_but_keeps_identity_and_actions(
    photo_url: str | None,
) -> None:
    bubble = animal_confirmation_bubble(
        animal_name="小森",
        shelter_number="A-001",
        area_label="北區 A3",
        organization_name="浪浪森友會 A",
        photo_url=photo_url,
        confirm_data="action=confirm_animal&animal_id=animal-a",
    )

    assert "hero" not in bubble["contents"]
    texts = _texts(bubble)
    assert {"A-001", "北區 A3", "浪浪森友會 A", "確認是這隻", "重新選擇"} <= set(texts)
    assert any("小森" in text for text in texts)


def test_today_list_has_two_sections_counts_local_time_and_pagination() -> None:
    bubble = daily_care_bubble(
        [
            ("小森／A-001", "action=select_animal&animal_id=a", "今天尚未回報", False),
            ("小白／A-002", "action=select_animal&animal_id=b", "已回報 2 次 · 最新 09:30", True),
        ],
        done=1,
        total=4,
        shown_through=2,
        more_data="action=today_overview&page=2",
    )

    texts = _texts(bubble)
    assert "尚未回報" in texts
    assert "今日已回報" in texts
    assert "已回報 2 次 · 最新 09:30" in texts
    assert "顯示更多（還有 2 隻）" in texts
