from uuid import uuid4

from services.api.app.domain.adoption_matching import (
    MAX_SCORE,
    AdopterPreferences,
    AnimalProfile,
    max_achievable_score,
    rank_animals,
    score_percentage,
)


def _preferences(**overrides: str) -> AdopterPreferences:
    base = dict(
        housing_type="house",
        dog_experience="experienced",
        other_pets="none",
        household_members="adults_only",
        work_schedule="retired",
        preferred_size="medium",
        preferred_energy="high",
    )
    base.update(overrides)
    return AdopterPreferences(**base)


def test_matching_size_and_energy_prefers_closer_match() -> None:
    better = AnimalProfile(animal_id=uuid4(), size="medium", energy="high")
    worse = AnimalProfile(animal_id=uuid4(), size="small", energy="low")

    ranked = rank_animals(_preferences(), [worse, better])

    assert ranked[0].animal_id == better.animal_id
    assert ranked[0].score > ranked[1].score


def test_non_adoptable_animals_are_excluded() -> None:
    adoptable = AnimalProfile(animal_id=uuid4(), size="medium", energy="high")
    not_adoptable = AnimalProfile(
        animal_id=uuid4(), size="medium", energy="high", is_adoptable=False
    )

    ranked = rank_animals(_preferences(), [adoptable, not_adoptable])

    assert [item.animal_id for item in ranked] == [adoptable.animal_id]


def test_top_n_truncates_results() -> None:
    candidates = [AnimalProfile(animal_id=uuid4(), size="medium", energy="high") for _ in range(5)]

    ranked = rank_animals(_preferences(), candidates, top_n=2)

    assert len(ranked) == 2


def test_ties_are_broken_deterministically_by_animal_id() -> None:
    candidates = [AnimalProfile(animal_id=uuid4(), size=None, energy=None) for _ in range(3)]

    first_run = rank_animals(_preferences(), candidates)
    second_run = rank_animals(_preferences(), candidates)

    assert [item.animal_id for item in first_run] == [item.animal_id for item in second_run]
    assert [str(item.animal_id) for item in first_run] == sorted(
        str(item.animal_id) for item in candidates
    )


def test_empty_candidate_list_returns_empty_result() -> None:
    assert rank_animals(_preferences(), []) == []


def test_temperament_and_schedule_bonuses_are_applied() -> None:
    cat_ok = AnimalProfile(animal_id=uuid4(), size="medium", energy="high", temperament=("cat_ok",))
    plain = AnimalProfile(animal_id=uuid4(), size="medium", energy="high")

    ranked = rank_animals(_preferences(other_pets="has_cats"), [plain, cat_ok])

    assert ranked[0].animal_id == cat_ok.animal_id
    assert "與貓咪相容" in ranked[0].reasons


def test_max_achievable_score_with_size_and_energy_preferences_equals_max_score() -> None:
    preferences = _preferences(preferred_size="medium", preferred_energy="high")

    assert max_achievable_score(preferences) == MAX_SCORE


def test_max_achievable_score_without_size_and_energy_preferences_is_smaller() -> None:
    """The 心有所屬 (specific-animal) path never collects preferred_size/
    preferred_energy, so its ceiling must be lower than MAX_SCORE — otherwise
    every specific-animal confirmation would be unfairly capped at 50%."""
    preferences = _preferences(preferred_size=None, preferred_energy=None)

    assert max_achievable_score(preferences) == MAX_SCORE - 4.0


def test_score_percentage_normalizes_against_the_achievable_ceiling() -> None:
    preferences = _preferences(preferred_size=None, preferred_energy=None)
    ceiling = max_achievable_score(preferences)

    assert score_percentage(ceiling, preferences) == 100
    assert score_percentage(0.0, preferences) == 0
    assert score_percentage(ceiling / 2, preferences) == 50


def test_score_percentage_clamps_to_0_100_range() -> None:
    preferences = _preferences()

    assert score_percentage(-5.0, preferences) == 0
    assert score_percentage(MAX_SCORE * 10, preferences) == 100
