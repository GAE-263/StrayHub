import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.domain.line_care_report_state import UNOBSERVED, WALK_COMPLETION_CODES


def test_unobserved_sentinel_is_not_a_walk_completion_code() -> None:
    assert UNOBSERVED not in WALK_COMPLETION_CODES


def test_effective_options_use_stable_codes_and_reject_disabled_options() -> None:
    service = EffectiveObservationService(
        {
            "gait.normal": EffectiveOption("gait.normal", "正常"),
            "appearance.other": EffectiveOption("appearance.other", "其他", requires_note=True),
            "gait.old": EffectiveOption("gait.old", "舊選項", active=False),
        }
    )

    assert service.is_valid("gait.normal")
    assert not service.is_valid("gait.old")
    service.validate_answer("gait", "gait.normal")


def test_options_that_require_note_cannot_be_submitted_without_note() -> None:
    service = EffectiveObservationService(
        {
            "appearance.other": EffectiveOption("appearance.other", "其他", requires_note=True),
        }
    )

    with pytest.raises(DomainError, match="補充說明"):
        service.validate_note_requirement({"appearance_special_status": "appearance.other"}, None)

    service.validate_note_requirement({"appearance_special_status": "appearance.other"}, "有補充")
