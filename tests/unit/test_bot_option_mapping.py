import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.application.line_message_presenter import question_bubble


def _service() -> EffectiveObservationService:
    return EffectiveObservationService(
        {
            "appearance.calm": EffectiveOption("appearance.calm", "平靜／放鬆"),
            "appearance.other": EffectiveOption("appearance.other", "其他", requires_note=True),
            "appearance.old": EffectiveOption("appearance.old", "舊名稱", active=False),
        }
    )


def test_flex_question_uses_display_name_for_label_and_stable_code_for_postback() -> None:
    payload = question_bubble(
        [_service().options["appearance.calm"]],
        draft_token="draft-1",
        step="appearance_special_status",
        title="身體外觀",
        position=6,
        total=6,
    )
    action = payload["contents"]["body"]["contents"][0]["action"]
    assert payload["type"] == "flex"
    assert action["label"] == "平靜／放鬆"
    assert "value=appearance.calm" in action["data"]
    assert action["displayText"] == "平靜／放鬆"


def test_mapping_is_a_whitelist_and_disabled_options_are_rejected() -> None:
    service = _service()
    assert service.is_valid("appearance.calm", category="appearance")
    assert not service.is_valid("appearance.calm", category="gait")
    assert not service.is_valid("appearance.injected")
    with pytest.raises(DomainError, match="無效或已停用"):
        service.validate_answer("appearance_special_status", "appearance.old")


def test_other_option_requires_a_supplement() -> None:
    service = _service()
    with pytest.raises(DomainError, match="補充說明"):
        service.validate_note_requirement({"appearance_special_status": "appearance.other"}, " ")
    service.validate_note_requirement(
        {"appearance_special_status": "appearance.other"}, "現場觀察到不同反應"
    )
