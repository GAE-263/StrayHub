import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.domain.line_care_report_state import UNOBSERVED


def test_effective_options_validate_frozen_categories() -> None:
    service = EffectiveObservationService({"gait.normal": EffectiveOption("gait.normal", "正常")})
    service.validate_answer("walk_completion", "walk_completion.completed")
    service.validate_answer("gait", "gait.normal")
    with pytest.raises(DomainError):
        service.validate_answer("feeding", "feeding.normal")


def test_disabled_option_is_rejected() -> None:
    service = EffectiveObservationService(
        {"gait.old": EffectiveOption("gait.old", "舊選項", active=False)}
    )
    assert not service.is_valid("gait.old")


def test_required_note_error_uses_human_label() -> None:
    service = EffectiveObservationService({
        "appearance.other": EffectiveOption("appearance.other", "其他", requires_note=True)
    })
    with pytest.raises(DomainError, match="其他"):
        service.validate_note_requirement({"appearance_special_status": "appearance.other"}, None)


def test_unobserved_is_not_a_crm_option() -> None:
    assert not EffectiveObservationService({}).is_valid(UNOBSERVED)
