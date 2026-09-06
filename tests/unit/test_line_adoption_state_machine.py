import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.line_adoption_state import (
    AdoptionDraftState,
    AdoptionDraftStateMachine,
    AdoptionInquiryAnswers,
    AdoptionPath,
    can_go_back,
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
    assert machine.state == AdoptionDraftState.AWAITING_FREETEXT_PROFILE
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

    # 方向 D: one free-text self-introduction round sits ahead of the
    # one-by-one questionnaire now — see AWAITING_FREETEXT_PROFILE.
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE)
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
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE)
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
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE, path=AdoptionPath.RECOMMEND_ME)
    machine.transition(AdoptionDraftState.ANSWERING_PREFERENCE_HOUSING)
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
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE)
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
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE)
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
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE)
    machine.transition(AdoptionDraftState.ANSWERING_HOUSING)
    machine.answer_question("housing_type", "apartment_small")
    machine.answer_question("dog_experience", "first_time")

    machine.back()

    assert machine.state == AdoptionDraftState.ANSWERING_EXPERIENCE
    assert machine.answers.values["housing_type"] == "apartment_small"
    assert "dog_experience" not in machine.answers.values


def test_back_out_of_choosing_path_resets_selected_path() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE, path=AdoptionPath.RECOMMEND_ME)

    machine.back()

    assert machine.state == AdoptionDraftState.CHOOSING_PATH
    assert machine.path is None


def test_skip_prefilled_questions_lands_on_first_genuine_gap() -> None:
    """方向 D: a free-text self-introduction can pre-fill some answers before
    the one-by-one flow starts — skip_prefilled_questions() should walk past
    every fully-answered ANSWERING_* state and stop at the first real gap."""
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE)
    # Simulate extraction pre-filling everything except work_schedule.
    for key, value in [
        ("housing_type", "apartment_small"),
        ("dog_experience", "first_time"),
        ("other_pets", "none"),
        ("household_members", "adults_only"),
    ]:
        machine.answers.set(key, value)

    machine.advance()  # AWAITING_FREETEXT_PROFILE -> ANSWERING_HOUSING
    machine.skip_prefilled_questions()

    assert machine.state == AdoptionDraftState.ANSWERING_SCHEDULE


def test_skip_prefilled_questions_reaches_confirming_answers_when_all_filled() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE)
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
        machine.answers.set(key, value)

    machine.advance()
    machine.skip_prefilled_questions()

    assert machine.state == AdoptionDraftState.CONFIRMING_ANSWERS


def test_skip_prefilled_questions_stops_at_presenting_matches_for_side_effects() -> None:
    """推薦名單's PRESENTING_MATCHES computes the rule-based candidate pool
    as a side effect the caller must trigger — skip_prefilled_questions()
    must not silently cross it even though it isn't a question-bearing
    state itself."""
    machine = _advance_to_choosing_path()
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE, path=AdoptionPath.RECOMMEND_ME)
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
        machine.answers.set(key, value)

    machine.advance()
    machine.skip_prefilled_questions()

    assert machine.state == AdoptionDraftState.PRESENTING_MATCHES


def test_submit_without_completing_required_answers_is_rejected() -> None:
    machine = _advance_to_choosing_path()
    machine.transition(
        AdoptionDraftState.SELECTING_TARGET_ANIMAL, path=AdoptionPath.SPECIFIC_ANIMAL
    )
    machine.transition(AdoptionDraftState.CONFIRMING_TARGET_ANIMAL)
    machine.transition(AdoptionDraftState.AWAITING_FREETEXT_PROFILE)
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


def test_can_go_back_is_false_only_at_the_very_first_step() -> None:
    """SELECTING_ORGANIZATION is the one state nothing precedes — every
    other state reachable in either path has a previous step to return to.
    line_webhook.py uses this to decide whether to offer a "回到上一頁"
    quick-reply."""
    assert can_go_back(AdoptionDraftState.SELECTING_ORGANIZATION, None) is False
    assert can_go_back(AdoptionDraftState.CHOOSING_PATH, None) is True
    assert (
        can_go_back(AdoptionDraftState.SELECTING_TARGET_ANIMAL, AdoptionPath.SPECIFIC_ANIMAL)
        is True
    )
    assert (
        can_go_back(AdoptionDraftState.AWAITING_FREETEXT_PROFILE, AdoptionPath.RECOMMEND_ME)
        is True
    )
    assert can_go_back(AdoptionDraftState.REVIEWING, None) is True


def test_can_go_back_agrees_with_back_actually_succeeding() -> None:
    machine = AdoptionDraftStateMachine()
    assert can_go_back(machine.state, machine.path) is False
    with pytest.raises(DomainError):
        machine.back()

    machine.transition(AdoptionDraftState.CHOOSING_PATH)
    assert can_go_back(machine.state, machine.path) is True
    machine.back()
    assert machine.state == AdoptionDraftState.SELECTING_ORGANIZATION
