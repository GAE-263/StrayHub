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

    # AI is optional, so confirming answers proceeds directly to contact data.
    assert machine.state == AdoptionDraftState.CONFIRMING_ANSWERS
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
    # Deterministic results are immediately selectable when AI is disabled.
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
    machine.transition(AdoptionDraftState.AWAITING_ADOPTER_NAME)
    machine.transition(AdoptionDraftState.AWAITING_CONTACT_TIME)
    machine.transition(AdoptionDraftState.AWAITING_PHONE_NUMBER)
    assert machine.state == AdoptionDraftState.AWAITING_PHONE_NUMBER

    with pytest.raises(DomainError, match="領養問卷"):
        machine.transition(AdoptionDraftState.REVIEWING)
