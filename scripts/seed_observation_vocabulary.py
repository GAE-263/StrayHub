"""Seed the platform's non-diagnostic Observation Vocabulary."""

from __future__ import annotations

from collections.abc import Iterable

# A walk report asks what a volunteer can actually observe during one walk —
# no shelter-side care, no subjective emotion reading. "Didn't observe" is a
# Bot-level sentinel (UNOBSERVED, line_care_report_state.py), not a CRM code,
# so it is never listed here. See docs/散步回報-題目與收集理由.md.
PLATFORM_OPTIONS: dict[str, tuple[str, ...]] = {
    "walk_completion": (
        "walk_completion.completed",
        "walk_completion.partially_completed",
        "walk_completion.not_done",
    ),
    "activity": (
        "activity.higher",
        "activity.usual",
        "activity.lower",
    ),
    "gait": (
        "gait.normal",
        "gait.off",
        "gait.abnormal",
    ),
    "defecation": (
        "defecation.normal",
        "defecation.soft",
        "defecation.none",
        "defecation.abnormal",
    ),
    "animal_interaction": (
        "animal_interaction.friendly",
        "animal_interaction.no_reaction",
        "animal_interaction.wary",
        "animal_interaction.no_encounter",
    ),
    "appearance_special_status": (
        "appearance.none_found",
        "appearance.skin_or_coat",
        "appearance.wound",
        "appearance.other",
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
