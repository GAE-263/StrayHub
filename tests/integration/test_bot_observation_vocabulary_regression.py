from pathlib import Path

from services.api.app.application.effective_observation_service import EffectiveOption
from services.api.app.application.line_message_presenter import question_bubble


def test_bot_presenter_has_no_business_vocabulary_copy() -> None:
    presenter = Path("services/api/app/application/line_message_presenter.py").read_text()
    webhook = Path("services/api/app/api/line_webhook.py").read_text()
    assert "appearance.none_found" not in presenter
    assert "appearance.none_found" not in webhook


def test_management_and_bot_share_the_same_code_and_effective_option_shape() -> None:
    option = EffectiveOption("appearance.us4", "新的外觀描述", requires_note=True)
    payload = question_bubble(
        [option],
        draft_token="same-draft",
        step="appearance_special_status",
        title="身體外觀",
        position=6,
        total=6,
    )
    action = payload["contents"]["body"]["contents"][0]["action"]
    assert payload["type"] == "flex"
    assert option.code in action["data"]
    assert option.display_name == action["label"]
    assert option.requires_note is True
