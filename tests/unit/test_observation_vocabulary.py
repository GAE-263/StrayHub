import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.domain.line_care_report_state import (
    CARE_COMPLETION_CODES,
    WALK_COMPLETION_CODES,
)


def test_completion_code_sets_are_distinct() -> None:
    assert CARE_COMPLETION_CODES.isdisjoint(WALK_COMPLETION_CODES)


def test_effective_options_use_stable_codes_and_reject_disabled_options() -> None:
    service = EffectiveObservationService(
        {
            "emotion.calm": EffectiveOption("emotion.calm", "平靜"),
            "emotion.other": EffectiveOption("emotion.other", "其他", requires_note=True),
            "emotion.old": EffectiveOption("emotion.old", "舊選項", active=False),
        }
    )

    assert service.is_valid("emotion.calm")
    assert not service.is_valid("emotion.old")
    service.validate_answer("care_completion", "care_completion.completed")


def test_options_that_require_note_cannot_be_submitted_without_note() -> None:
    service = EffectiveObservationService(
        {
            "emotion.other": EffectiveOption("emotion.other", "其他", requires_note=True),
        }
    )

    with pytest.raises(DomainError, match="補充說明"):
        service.validate_note_requirement({"emotion": "emotion.other"}, None)

    service.validate_note_requirement({"emotion": "emotion.other"}, "有補充")
