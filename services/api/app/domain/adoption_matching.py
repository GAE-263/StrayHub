from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AdopterPreferences:
    housing_type: str
    dog_experience: str
    other_pets: str
    household_members: str
    work_schedule: str
    preferred_size: str | None = None
    preferred_energy: str | None = None


@dataclass(frozen=True)
class AnimalProfile:
    animal_id: UUID
    size: str | None
    energy: str | None
    temperament: tuple[str, ...] = ()
    is_adoptable: bool = True


@dataclass(frozen=True)
class MatchScore:
    animal_id: UUID
    score: float
    reasons: tuple[str, ...]


_LOW_ENERGY_SCHEDULES = {"full_time_work", "little_time_at_home"}
_HIGH_ENERGY_SCHEDULES = {"work_from_home", "flexible", "retired"}
_SMALL_HOUSING = {"apartment_small"}


def rank_animals(
    preferences: AdopterPreferences,
    candidates: list[AnimalProfile],
    *,
    top_n: int = 3,
) -> list[MatchScore]:
    """Deterministic, rule-based ranking. No I/O — callers must pre-filter
    candidates to `is_adoptable=True` animals in the correct organization."""
    scored = [_score(preferences, candidate) for candidate in candidates if candidate.is_adoptable]
    scored.sort(key=lambda item: (-item.score, str(item.animal_id)))
    return scored[:top_n]


def score_single(preferences: AdopterPreferences, animal: AnimalProfile) -> MatchScore:
    """Score one already-chosen animal against the adopter's preferences.

    For the 心有所屬 (specific-animal) path, where the animal is picked before
    preferences are collected — unlike `rank_animals`, which filters/ranks a
    candidate pool for the 推薦我 (recommend-me) path."""
    return _score(preferences, animal)


def _score(preferences: AdopterPreferences, animal: AnimalProfile) -> MatchScore:
    score = 0.0
    reasons: list[str] = []

    if preferences.preferred_size and animal.size and preferences.preferred_size == animal.size:
        score += 2
        reasons.append("體型符合偏好")

    if (
        preferences.preferred_energy
        and animal.energy
        and preferences.preferred_energy == animal.energy
    ):
        score += 2
        reasons.append("活動力符合偏好")

    if preferences.other_pets == "has_cats" and "cat_ok" in animal.temperament:
        score += 1
        reasons.append("與貓咪相容")
    if preferences.other_pets == "has_dogs" and "dog_ok" in animal.temperament:
        score += 1
        reasons.append("與其他狗狗相容")
    if preferences.household_members == "has_children" and "kid_ok" in animal.temperament:
        score += 1
        reasons.append("適合有小孩的家庭")

    if preferences.work_schedule in _LOW_ENERGY_SCHEDULES and animal.energy == "low":
        score += 1
        reasons.append("適合工作時間較長的家庭")
    elif preferences.work_schedule in _HIGH_ENERGY_SCHEDULES and animal.energy == "high":
        score += 1
        reasons.append("適合有較多時間陪伴的家庭")

    if preferences.housing_type in _SMALL_HOUSING and animal.size == "small":
        score += 1
        reasons.append("適合小坪數居住空間")

    return MatchScore(animal_id=animal.animal_id, score=score, reasons=tuple(reasons))
