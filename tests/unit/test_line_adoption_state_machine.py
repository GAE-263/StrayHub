import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.line_adoption_state import (
    AdoptionDraftState,
    AdoptionDraftStateMachine,
    AdoptionInquiryAnswers,
    AdoptionPath,
)


def _advance_to_choosing_path() -> AdoptionDraftStateMachine:
    machine = AdoptionDraftStateMachine()
    machine.transition(AdoptionDraftState.CHOOSING_PATH)
    return machine


def test_advance_and_choose_path_convenience_methods_mirror_transition() -> None:
    machine = AdoptionDraftStateMachine()

    machine.advance()
    assert machine.state == AdoptionDraftState.CHOOSING_PATH

    machine.choose_path(AdoptionPath.RECOMMEND_ME)
    assert machine.state == AdoptionDraftState.ANSWERING_PREFERENCE_HOUSING
    assert machine.path == AdoptionPath.RECOMMEND_ME


def test_choosing_path_requires_explicit_path() -> None:
    machine = _advance_to_choosing_path()

    with pytest.raises(DomainError, match="路徑"):
        machine.transition(AdoptionDraftState.SELECTING_TARGET_ANIMAL)


def test_specific_animal_path_walks_through_shared_questionnaire_and_submits() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    assert machine.state == AdoptionDraftState.CONFIRMING_TARGET_ANIMAL

    machine.transition(AdoptionDraftState.ANSWERING_HOUSING)
    for key, value in [
        ("housing_type", "apartment_small"),
        ("dog_experience", "first_time"),
        ("other_pets", "none"),
        ("household_members", "adults_only"),
        ("work_schedule", "work_from_home"),
        ("parenting_style", "structured"),
        ("patience_level", "high_patience"),
        ("adoption_motivation", "companionship"),
    ]:
        machine.answer_question(key, value)

    # Finishing the questionnaire pauses for a reconfirm-your-answers
    # checkpoint, then an "AI is analyzing" wait — neither is skippable by
    # answering more questions, only by the dedicated confirm_answers action
    # or (for AI) the background analysis task itself moving the draft on.
    assert machine.state == AdoptionDraftState.CONFIRMING_ANSWERS
    machine.transition(AdoptionDraftState.AWAITING_AI_SUITABILITY)
    assert machine.state == AdoptionDraftState.AWAITING_AI_SUITABILITY

    # In production this next hop is driven by the AI background task
    # itself, not a user action — simulated here directly.
    machine.transition(AdoptionDraftState.AWAITING_ADOPTER_NAME)
    machine.answer_question("adopter_name", "王小明")
    assert machine.state == AdoptionDraftState.AWAITING_CONTACT_TIME
    machine.answer_question("contact_time", "平日白天（9-18點）")
    assert machine.state == AdoptionDraftState.AWAITING_PHONE_NUMBER
    machine.answer_question("phone_number", "0912345678")
    assert machine.state == AdoptionDraftState.REVIEWING

    machine.transition(AdoptionDraftState.SUBMITTING)
    answers = machine.submit()

    assert isinstance(answers, AdoptionInquiryAnswers)
    assert answers.path == AdoptionPath.SPECIFIC_ANIMAL
    assert machine.state == AdoptionDraftState.SUBMITTED


def test_confirming_answers_back_returns_to_last_question_and_clears_it() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    machine.transition(AdoptionDraftState.ANSWERING_HOUSING)
    for key, value in [
        ("housing_type", "apartment_small"),
        ("dog_experience", "first_time"),
        ("other_pets", "none"),
        ("household_members", "adults_only"),
        ("work_schedule", "work_from_home"),
        ("parenting_style", "structured"),
        ("patience_level", "high_patience"),
        ("adoption_motivation", "companionship"),
    ]:
        machine.answer_question(key, value)
    assert machine.state == AdoptionDraftState.CONFIRMING_ANSWERS

    machine.back()

    assert machine.state == AdoptionDraftState.ANSWERING_ADOPTION_MOTIVATION
    assert "adoption_motivation" not in machine.answers.values
    assert machine.answers.values["patience_level"] == "high_patience"


def test_recommend_me_path_asks_extra_preferences_and_skips_shared_questionnaire() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.ANSWERING_PREFERENCE_HOUSING, path=AdoptionPath.RECOMMEND_ME
    )
    for key, value in [
        ("housing_type", "house"),
        ("dog_experience", "experienced"),
        ("other_pets", "has_cats"),
        ("household_members", "has_children"),
        ("work_schedule", "retired"),
        ("parenting_style", "free"),
        ("patience_level", "medium_patience"),
        ("adoption_motivation", "family_activity"),
        ("preferred_size", "medium"),
        ("preferred_energy", "high"),
    ]:
        machine.answer_question(key, value)

    assert machine.state == AdoptionDraftState.PRESENTING_MATCHES
    # PRESENTING_MATCHES pauses at AWAITING_AI_RECOMMENDATIONS for the AI
    # background task to rerank the rule-based pool — in production this
    # next hop is driven by that task, not a user action.
    machine.transition(AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS)
    machine.transition(AdoptionDraftState.SELECTING_MATCHED_ANIMAL)
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)

    # Path 2 already collected preferences pre-matching, so the shared per-animal
    # questionnaire (ANSWERING_HOUSING etc.) must NOT be asked again.
    assert machine.state == AdoptionDraftState.CONFIRMING_TARGET_ANIMAL
    machine.transition(AdoptionDraftState.AWAITING_ADOPTER_NAME)
    machine.answer_question("adopter_name", "王小明")
    machine.answer_question("contact_time", "假日皆可")
    machine.answer_question("phone_number", "0987654321")
    assert machine.state == AdoptionDraftState.REVIEWING


def test_specific_animal_low_score_alternative_flow_reaches_adopter_name() -> None:
    """A low AI score doesn't jump straight to contact info — the background
    followup-recommendation task drops the draft at SELECTING_ALTERNATIVE_ANIMAL
    (see line_webhook.py), and the adopter must pick-then-confirm a target
    (possibly the same one, possibly a new one) before contact info is asked."""
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    machine.transition(AdoptionDraftState.ANSWERING_HOUSING)
    for key, value in [
        ("housing_type", "apartment_small"),
        ("dog_experience", "first_time"),
        ("other_pets", "none"),
        ("household_members", "adults_only"),
        ("work_schedule", "work_from_home"),
        ("parenting_style", "structured"),
        ("patience_level", "high_patience"),
        ("adoption_motivation", "companionship"),
    ]:
        machine.answer_question(key, value)
    machine.transition(AdoptionDraftState.AWAITING_AI_SUITABILITY)

    # AI came back <60%, adopter answered the free-text follow-up — the
    # background task moves the draft here by writing draft.current_step
    # directly (see line_webhook.py), not via machine.transition()/advance(),
    # so the next request reconstructs the machine straight into this state —
    # simulated here the same way rather than calling transition() on the
    # existing instance (which would correctly reject it as a second,
    # data-dependent target from AWAITING_AI_SUITABILITY).
    machine = AdoptionDraftStateMachine(
        state=AdoptionDraftState.SELECTING_ALTERNATIVE_ANIMAL,
        path=machine.path,
        answers=machine.answers,
    )
    machine.transition(AdoptionDraftState.CONFIRMING_ALTERNATIVE_ANIMAL)
    assert machine.state == AdoptionDraftState.CONFIRMING_ALTERNATIVE_ANIMAL

    # "不是，重新選一隻" goes back to the same alternatives list, not further.
    machine.back()
    assert machine.state == AdoptionDraftState.SELECTING_ALTERNATIVE_ANIMAL

    machine.transition(AdoptionDraftState.CONFIRMING_ALTERNATIVE_ANIMAL)
    machine.transition(AdoptionDraftState.AWAITING_ADOPTER_NAME)
    assert machine.state == AdoptionDraftState.AWAITING_ADOPTER_NAME


def test_invalid_phone_number_is_rejected() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    machine.transition(AdoptionDraftState.ANSWERING_HOUSING)
    for key, value in [
        ("housing_type", "apartment_small"),
        ("dog_experience", "first_time"),
        ("other_pets", "none"),
        ("household_members", "adults_only"),
        ("work_schedule", "work_from_home"),
        ("parenting_style", "structured"),
        ("patience_level", "high_patience"),
        ("adoption_motivation", "companionship"),
    ]:
        machine.answer_question(key, value)
    machine.transition(AdoptionDraftState.AWAITING_AI_SUITABILITY)
    machine.transition(AdoptionDraftState.AWAITING_ADOPTER_NAME)
    machine.answer_question("adopter_name", "王小明")
    machine.answer_question("contact_time", "平日白天（9-18點）")

    with pytest.raises(DomainError, match="手機號碼"):
        machine.answer_question("phone_number", "not-a-phone")


def test_back_from_answering_state_clears_that_and_later_answers() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    machine.transition(AdoptionDraftState.ANSWERING_HOUSING)
    machine.answer_question("housing_type", "apartment_small")
    machine.answer_question("dog_experience", "first_time")

    machine.back()

    assert machine.state == AdoptionDraftState.ANSWERING_EXPERIENCE
    assert machine.answers.values["housing_type"] == "apartment_small"
    assert "dog_experience" not in machine.answers.values


def test_back_out_of_choosing_path_resets_selected_path() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.ANSWERING_PREFERENCE_HOUSING, path=AdoptionPath.RECOMMEND_ME
    )

    machine.back()

    assert machine.state == AdoptionDraftState.CHOOSING_PATH
    assert machine.path is None


def test_submit_without_completing_required_answers_is_rejected() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    machine.transition(AdoptionDraftState.ANSWERING_HOUSING)
    for key, value in [
        ("housing_type", "apartment_small"),
        ("dog_experience", "first_time"),
        ("other_pets", "none"),
        ("household_members", "adults_only"),
        ("work_schedule", "work_from_home"),
        ("parenting_style", "structured"),
        ("patience_level", "high_patience"),
        ("adoption_motivation", "companionship"),
    ]:
        machine.answer_question(key, value)
    machine.transition(AdoptionDraftState.AWAITING_AI_SUITABILITY)
    machine.transition(AdoptionDraftState.AWAITING_ADOPTER_NAME)
    machine.transition(AdoptionDraftState.AWAITING_CONTACT_TIME)
    machine.transition(AdoptionDraftState.AWAITING_PHONE_NUMBER)
    assert machine.state == AdoptionDraftState.AWAITING_PHONE_NUMBER

    with pytest.raises(DomainError, match="領養問卷"):
        machine.transition(AdoptionDraftState.REVIEWING)


@pytest.mark.parametrize(
    "key,value",
    [("adopter_name", "陳小明"), ("contact_time", "假日下午"), ("phone_number", "0987654321")],
)
def test_contact_edit_preserves_other_answers_and_returns_to_review(key, value):
    machine = AdoptionDraftStateMachine(state=AdoptionDraftState.REVIEWING)
    machine.answers.values = {
        "adopter_name": "王小明",
        "contact_time": "平日白天",
        "phone_number": "0912345678",
        "housing_type": "house",
    }
    before = dict(machine.answers.values)
    machine.edit_contact(key)
    machine.save_contact(value)
    assert machine.state == AdoptionDraftState.REVIEWING
    assert machine.answers.values == {**before, key: value}


def test_invalid_contact_edit_preserves_previous_phone_and_can_cancel():
    machine = AdoptionDraftStateMachine(state=AdoptionDraftState.REVIEWING)
    machine.answers.values = {"phone_number": "0912345678"}
    machine.edit_contact("phone_number")
    with pytest.raises(DomainError):
        machine.save_contact("123")
    assert machine.answers.values["phone_number"] == "0912345678"
    assert machine.state == AdoptionDraftState.EDITING_PHONE_NUMBER
    machine.cancel_contact_edit()
    assert machine.state == AdoptionDraftState.REVIEWING
    with pytest.raises(DomainError):
        machine.save_contact("0987654321")


def test_repair_incomplete_draft_preserves_answers_and_returns_to_first_missing():
    machine = AdoptionDraftStateMachine(
        state=AdoptionDraftState.CONFIRMING_ANSWERS,
        path=AdoptionPath.SPECIFIC_ANIMAL,
    )
    machine.answers.values = {
        "dog_experience": "first_time",
        "parenting_style": "structured",
    }

    missing = machine.repair_to_first_missing(
        (
            "housing_type",
            "dog_experience",
            "parenting_style",
        )
    )

    assert missing == "housing_type"
    assert machine.state == AdoptionDraftState.ANSWERING_HOUSING
    assert machine.answers.values == {
        "dog_experience": "first_time",
        "parenting_style": "structured",
    }


def test_resume_repairs_missing_answers_before_saved_step():
    machine = AdoptionDraftStateMachine(
        state=AdoptionDraftState.ANSWERING_ADOPTION_MOTIVATION,
        path=AdoptionPath.SPECIFIC_ANIMAL,
    )
    machine.answers.values = {
        "other_pets": "none",
        "household_members": "adults_only",
        "work_schedule": "work_from_home",
        "parenting_style": "structured",
        "patience_level": "high_patience",
    }

    assert machine.repair_for_resume() == "housing_type"
    assert machine.state == AdoptionDraftState.ANSWERING_HOUSING
    assert machine.answers.values["parenting_style"] == "structured"


def test_saved_answer_on_current_question_can_be_reconfirmed_and_advanced():
    machine = AdoptionDraftStateMachine(
        state=AdoptionDraftState.ANSWERING_OTHER_PETS,
        path=AdoptionPath.SPECIFIC_ANIMAL,
    )
    machine.answers.values = {
        "housing_type": "apartment_small",
        "dog_experience": "first_time",
        "other_pets": "none",
    }

    assert machine.prepare_answer_replay("other_pets") is True
    assert machine.answer_current("cat") == AdoptionDraftState.ANSWERING_HOUSEHOLD
    assert machine.answers.values["other_pets"] == "cat"
