import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import (
    REQUIRED_ANSWER_KEYS,
    UNOBSERVED,
    WALK_COMPLETION_CODES,
    CareReportAnswers,
    DraftState,
    DraftStateMachine,
)


def complete_answers() -> dict[str, str]:
    answers = {key: f"{key}.observed" for key in REQUIRED_ANSWER_KEYS}
    answers["walk_completion"] = next(iter(WALK_COMPLETION_CODES))
    return answers


def test_missing_required_answer_cannot_enter_reviewing() -> None:
    machine = DraftStateMachine(state=DraftState.AWAITING_STORY)

    with pytest.raises(DomainError, match="完成 6 個"):
        machine.transition(DraftState.REVIEWING)


def test_complete_answers_can_submit() -> None:
    machine = DraftStateMachine(state=DraftState.AWAITING_STORY)
    for key, value in complete_answers().items():
        machine.answer(key, value)

    machine.transition(DraftState.REVIEWING)
    machine.transition(DraftState.SUBMITTING)
    answers = machine.submit()

    assert isinstance(answers, CareReportAnswers)
    assert machine.state == DraftState.SUBMITTED


def test_walk_completion_must_be_a_known_code_or_unobserved() -> None:
    answers = complete_answers()
    answers["walk_completion"] = "not_a_real_code"

    with pytest.raises(DomainError, match="無效"):
        CareReportAnswers(answers)

    answers["walk_completion"] = UNOBSERVED
    CareReportAnswers(answers)  # does not raise


def test_state_machine_rejects_wrong_key_then_advances_on_correct_key() -> None:
    machine = DraftStateMachine(state=DraftState.ANSWERING_WALK_COMPLETION)

    with pytest.raises(DomainError, match="目前步驟"):
        machine.answer_question("activity", "activity.usual")
    machine.answer_question("walk_completion", "walk_completion.completed")

    assert machine.state == DraftState.ANSWERING_ACTIVITY


def test_back_clears_previous_step_answers_before_reanswering() -> None:
    machine = DraftStateMachine(state=DraftState.ANSWERING_GAIT)
    machine.answers.values.update(
        {
            "walk_completion": "walk_completion.completed",
            "activity": "activity.usual",
        }
    )

    assert machine.back() == DraftState.ANSWERING_ACTIVITY
    assert "activity" not in machine.answers.values
    assert machine.answers.values["walk_completion"] == "walk_completion.completed"
    assert machine.next_answer_key() == "activity"


def test_every_defecation_answer_lands_on_stool_media_first() -> None:
    """The raw state machine always stops at AWAITING_STOOL_MEDIA after
    defecation, regardless of the answer; skipping past it for "no stool" is a
    caller-side decision (see LineDraftConversationService), not something the
    fixed 1:1 _NEXT_STATES table can branch on."""
    machine = DraftStateMachine(state=DraftState.ANSWERING_DEFECATION)
    machine.answers.values.update(
        {
            "walk_completion": "walk_completion.completed",
            "activity": "activity.usual",
            "gait": "gait.normal",
        }
    )

    machine.answer_question("defecation", "defecation.none")

    assert machine.state == DraftState.AWAITING_STOOL_MEDIA
