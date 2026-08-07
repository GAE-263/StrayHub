from services.api.app.application.effective_observation_service import EffectiveOption
from services.api.app.application.line_message_presenter import quick_reply_for_options


def test_quick_reply_uses_stable_code_in_postback_and_limits_items() -> None:
    options = [EffectiveOption(f"emotion.{index}", f"選項 {index}") for index in range(8)]

    message = quick_reply_for_options(options, draft_token="opaque", step="emotion")
    items = message["quickReply"]["items"]

    assert len(items) == 6
    assert "value=emotion.0" in items[0]["action"]["data"]
    assert items[0]["action"]["label"] == "選項 0"
