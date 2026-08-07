"""Seed the platform's non-diagnostic Observation Vocabulary."""

from __future__ import annotations

from collections.abc import Iterable

PLATFORM_OPTIONS: dict[str, tuple[str, ...]] = {
    "care_completion": (
        "care_completion.completed",
        "care_completion.partially_completed",
        "care_completion.not_provided",
        "care_completion.not_observed",
        "care_completion.uncertain",
    ),
    "walk_completion": (
        "walk_completion.completed",
        "walk_completion.partially_completed",
        "walk_completion.not_done",
        "walk_completion.not_observed",
        "walk_completion.uncertain",
    ),
    "feeding": (
        "feeding.normal",
        "feeding.less",
        "feeding.almost_none",
        "feeding.not_provided",
        "feeding.not_observed",
        "feeding.uncertain",
    ),
    "water": (
        "water.observed",
        "water.less",
        "water.not_observed",
        "water.not_provided",
        "water.uncertain",
    ),
    "activity": (
        "activity.usual",
        "activity.lower",
        "activity.higher",
        "activity.unwilling",
        "activity.not_observed",
        "activity.uncertain",
    ),
    "urination": ("urination.observed", "urination.not_observed", "urination.uncertain"),
    "defecation": (
        "defecation.formed",
        "defecation.soft",
        "defecation.watery",
        "defecation.different_color",
        "defecation.different_shape",
        "defecation.not_observed",
        "defecation.uncertain",
    ),
    "resource_guarding": (
        "resource_guarding.not_observed",
        "resource_guarding.tense",
        "resource_guarding.vocalizes",
        "resource_guarding.blocks",
        "resource_guarding.moves_food",
        "resource_guarding.no_approach",
        "resource_guarding.uncertain",
        "resource_guarding.other",
    ),
    "human_interaction": (
        "human_interaction.usual",
        "human_interaction.seeking",
        "human_interaction.avoidant",
        "human_interaction.uncertain",
        "human_interaction.other",
    ),
    "animal_interaction": (
        "animal_interaction.usual",
        "animal_interaction.calm",
        "animal_interaction.avoidant",
        "animal_interaction.uncertain",
        "animal_interaction.other",
    ),
    "emotion": (
        "emotion.usual",
        "emotion.calm",
        "emotion.alert",
        "emotion.excited",
        "emotion.tense",
        "emotion.withdrawn",
        "emotion.seeking_interaction",
        "emotion.not_observed",
        "emotion.uncertain",
        "emotion.other",
    ),
    "walk": (
        "walk.usual",
        "walk.willing",
        "walk.exploring",
        "walk.reluctant",
        "walk.slow_or_stopping",
        "walk.tries_to_return",
        "walk.human_reaction",
        "walk.animal_reaction",
        "walk.not_done",
        "walk.not_observed",
        "walk.uncertain",
        "walk.other",
    ),
    "appearance_special_status": (
        "appearance.changed",
        "appearance.scratching",
        "appearance.red_area",
        "appearance.reduced_hair",
        "appearance.lying_long",
        "appearance.different_walk",
        "appearance.other",
        "appearance.not_observed",
        "appearance.uncertain",
    ),
}


def iter_platform_options() -> Iterable[tuple[str, str]]:
    for category, codes in PLATFORM_OPTIONS.items():
        for code in codes:
            yield category, code


def main() -> None:
    for category, code in iter_platform_options():
        print(f"{category}\t{code}")


if __name__ == "__main__":
    main()
