import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import (
    NO_STOOL_CODE,
    REQUIRED_ANSWER_KEYS,
    UNOBSERVED,
    CareReportAnswers,
    DraftState,
    DraftStateMachine,
)


def complete_answers() -> dict[str, str]:
    return {
        "walk_completion": "walk_completion.completed",
        "activity": "activity.usual",
        "gait": "gait.normal",
        "defecation": "defecation.normal",
        "animal_interaction": "animal_interaction.friendly",
        "appearance_special_status": "appearance.none_found",
    }


def test_frozen_six_question_contract() -> None:
    assert REQUIRED_ANSWER_KEYS == (
        "walk_completion",
        "activity",
        "gait",
        "defecation",
        "animal_interaction",
        "appearance_special_status",
    )


def test_missing_required_answer_cannot_enter_reviewing() -> None:
    machine = DraftStateMachine(state=DraftState.AWAITING_STORY)
    with pytest.raises(DomainError, match="完成 6 個"):
        machine.transition(DraftState.REVIEWING)


def test_complete_answers_can_submit() -> None:
    machine = DraftStateMachine(state=DraftState.AWAITING_STORY)
    machine.answers.values.update(complete_answers())
    machine.transition(DraftState.REVIEWING)
    machine.transition(DraftState.SUBMITTING)
    assert isinstance(machine.submit(), CareReportAnswers)


def test_forward_sequence_and_stool_photo_branch() -> None:
    machine = DraftStateMachine(state=DraftState.ANSWERING_WALK_COMPLETION)
    for value, state in (
        ("walk_completion.completed", DraftState.ANSWERING_ACTIVITY),
        ("activity.usual", DraftState.ANSWERING_GAIT),
        ("gait.normal", DraftState.ANSWERING_DEFECATION),
        ("defecation.normal", DraftState.AWAITING_STOOL_MEDIA),
    ):
        assert machine.answer_current(value) == state
    machine.transition(DraftState.ANSWERING_ANIMAL_INTERACTION)
    machine.answer_current("animal_interaction.friendly")
    machine.answer_current("appearance.none_found")
    assert machine.state == DraftState.AWAITING_NOTE


@pytest.mark.parametrize("value", [NO_STOOL_CODE, UNOBSERVED])
def test_no_stool_values_are_valid_domain_answers(value: str) -> None:
    machine = DraftStateMachine(state=DraftState.ANSWERING_DEFECATION)
    machine.answer_current(value)
    assert machine.state == DraftState.AWAITING_STOOL_MEDIA


def test_back_from_q5_skips_stool_prompt_when_no_stool() -> None:
    machine = DraftStateMachine(state=DraftState.ANSWERING_ANIMAL_INTERACTION)
    machine.answers.values.update(
        {
            "walk_completion": "walk_completion.completed",
            "activity": "activity.usual",
            "gait": "gait.normal",
            "defecation": NO_STOOL_CODE,
        }
    )
    assert machine.back() == DraftState.ANSWERING_DEFECATION
    assert "defecation" not in machine.answers.values


def test_unexpected_key_is_rejected() -> None:
    machine = DraftStateMachine(state=DraftState.ANSWERING_ACTIVITY)
    with pytest.raises(DomainError, match="目前步驟"):
        machine.answer_question("gait", "gait.normal")
