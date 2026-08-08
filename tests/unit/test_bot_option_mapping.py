import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.application.line_message_presenter import quick_reply_for_options


def _service() -> EffectiveObservationService:
    return EffectiveObservationService(
        {
            "emotion.calm": EffectiveOption("emotion.calm", "平靜／放鬆"),
            "emotion.other": EffectiveOption("emotion.other", "其他", requires_note=True),
            "emotion.old": EffectiveOption("emotion.old", "舊名稱", active=False),
        }
    )


def test_quick_reply_uses_display_name_for_label_and_stable_code_for_postback() -> None:
    payload = quick_reply_for_options(
        [_service().options["emotion.calm"]], draft_token="draft-1", step="emotion"
    )
    action = payload["quickReply"]["items"][0]["action"]
    assert action["label"] == "平靜／放鬆"
    assert "value=emotion.calm" in action["data"]
    assert action["displayText"] == "平靜／放鬆"


def test_mapping_is_a_whitelist_and_disabled_options_are_rejected() -> None:
    service = _service()
    assert service.is_valid("emotion.calm", category="emotion")
    assert not service.is_valid("emotion.calm", category="walk")
    assert not service.is_valid("emotion.injected")
    with pytest.raises(DomainError, match="無效或已停用"):
        service.validate_answer("emotion", "emotion.old")


def test_other_option_requires_a_supplement() -> None:
    service = _service()
    with pytest.raises(DomainError, match="補充說明"):
        service.validate_note_requirement({"emotion": "emotion.other"}, " ")
    service.validate_note_requirement({"emotion": "emotion.other"}, "現場觀察到不同反應")
