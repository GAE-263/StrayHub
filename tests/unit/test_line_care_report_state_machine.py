import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import (
    CARE_COMPLETION_CODES,
    REQUIRED_ANSWER_KEYS,
    WALK_COMPLETION_CODES,
    CareReportAnswers,
    DraftState,
    DraftStateMachine,
)


def complete_answers() -> dict[str, str]:
    answers = {key: f"{key}.observed" for key in REQUIRED_ANSWER_KEYS}
    answers["care_completion"] = next(iter(CARE_COMPLETION_CODES))
    answers["walk_completion"] = next(iter(WALK_COMPLETION_CODES))
    answers["walk_reaction"] = "walk.willing"
    return answers


def test_missing_required_answer_cannot_enter_reviewing() -> None:
    machine = DraftStateMachine(state=DraftState.AWAITING_NOTE)

    with pytest.raises(DomainError, match="完成 13 個"):
        machine.transition(DraftState.REVIEWING)


def test_complete_answers_can_submit_and_keep_completion_codes_separate() -> None:
    machine = DraftStateMachine(state=DraftState.AWAITING_NOTE)
    for key, value in complete_answers().items():
        machine.answer(key, value)

    machine.transition(DraftState.REVIEWING)
    machine.transition(DraftState.SUBMITTING)
    answers = machine.submit()

    assert isinstance(answers, CareReportAnswers)
    assert machine.state == DraftState.SUBMITTED


def test_walk_completion_code_cannot_be_used_as_walk_reaction() -> None:
    answers = complete_answers()
    answers["walk_reaction"] = "walk_completion.completed"

    with pytest.raises(DomainError, match="不可混用"):
        CareReportAnswers(answers)


def test_state_machine_accepts_completion_questions_in_order() -> None:
    machine = DraftStateMachine(state=DraftState.ANSWERING_COMPLETION)

    machine.answer_question("care_completion", "care_completion.completed")
    assert machine.state == DraftState.ANSWERING_COMPLETION
    with pytest.raises(DomainError, match="目前步驟"):
        machine.answer_question("feeding", "feeding.normal")
    machine.answer_question("walk_completion", "walk_completion.completed")
    assert machine.state == DraftState.ANSWERING_FEEDING


def test_back_clears_previous_step_answers_before_reanswering() -> None:
    machine = DraftStateMachine(state=DraftState.ANSWERING_WATER)
    machine.answers.values.update(
        {
            "care_completion": "care_completion.completed",
            "walk_completion": "walk_completion.completed",
            "feeding": "feeding.normal",
        }
    )

    assert machine.back() == DraftState.ANSWERING_FEEDING
    assert "feeding" not in machine.answers.values
    assert machine.answers.values["care_completion"] == "care_completion.completed"
    assert machine.answers.values["walk_completion"] == "walk_completion.completed"
    assert machine.next_answer_key() == "feeding"
