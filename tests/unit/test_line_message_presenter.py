from services.api.app.application.effective_observation_service import EffectiveOption
from services.api.app.application.line_message_presenter import question_bubble


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
    options = [EffectiveOption(f"emotion.{index}", f"選項 {index}") for index in range(8)]

    bubble = question_bubble(
        options, draft_token="opaque", step="emotion", title="情緒", position=11, total=13
    )
    actions = _option_actions(bubble)

    assert "value=emotion.0" in actions[0]["data"]
    assert actions[0]["label"] == "選項 0"


def test_question_bubble_offers_every_option() -> None:
    options = [EffectiveOption(f"walk.{index}", f"選項 {index}") for index in range(12)]

    bubble = question_bubble(
        options, draft_token="opaque", step="walk", title="散步", position=12, total=13
    )

    assert len(_option_actions(bubble)) == 12


def test_question_bubble_states_which_question_is_being_asked() -> None:
    bubble = question_bubble(
        [EffectiveOption("feeding.normal", "正常")],
        draft_token="opaque",
        step="feeding",
        title="進食",
        position=3,
        total=13,
    )

    header_texts = _texts(bubble["contents"]["header"])
    assert "進食" in header_texts
    assert any("3" in text and "13" in text for text in header_texts)
    assert "進食" in bubble["altText"]


def test_question_bubble_without_options_explains_instead_of_showing_nothing() -> None:
    bubble = question_bubble(
        [], draft_token="opaque", step="feeding", title="進食", position=3, total=13
    )

    assert _option_actions(bubble) == []
    assert bubble["contents"]["body"]["contents"][0]["text"]
