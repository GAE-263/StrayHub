from pathlib import Path

from services.api.app.application.effective_observation_service import EffectiveOption
from services.api.app.application.line_message_presenter import quick_reply_for_options


def test_bot_presenter_has_no_business_vocabulary_copy() -> None:
    presenter = Path("services/api/app/application/line_message_presenter.py").read_text()
    webhook = Path("services/api/app/api/line_webhook.py").read_text()
    assert "emotion.calm" not in presenter
    assert "emotion.calm" not in webhook


def test_management_and_bot_share_the_same_code_and_effective_option_shape() -> None:
    option = EffectiveOption("emotion.us4", "新的情緒描述", requires_note=True)
    payload = quick_reply_for_options([option], draft_token="same-draft", step="emotion")
    action = payload["quickReply"]["items"][0]["action"]
    assert option.code in action["data"]
    assert option.display_name == action["label"]
    assert option.requires_note is True
