from scripts.seed_observation_vocabulary import PLATFORM_OPTIONS


def test_platform_seed_contains_standard_required_vocabulary() -> None:
    required = {
        "walk_completion.completed",
        "walk_completion.partially_completed",
        "walk_completion.not_done",
        "activity.higher",
        "activity.usual",
        "activity.lower",
        "gait.normal",
        "gait.off",
        "gait.abnormal",
        "defecation.normal",
        "defecation.soft",
        "defecation.none",
        "defecation.abnormal",
        "animal_interaction.friendly",
        "animal_interaction.no_reaction",
        "animal_interaction.wary",
        "animal_interaction.no_encounter",
        "appearance.none_found",
        "appearance.skin_or_coat",
        "appearance.wound",
        "appearance.other",
    }
    actual = {code for codes in PLATFORM_OPTIONS.values() for code in codes}
    assert actual == required


def test_platform_seed_has_all_standard_answer_categories_and_other_requires_note() -> None:
    expected_categories = {
        "walk_completion",
        "activity",
        "gait",
        "defecation",
        "animal_interaction",
        "appearance_special_status",
    }
    assert expected_categories == set(PLATFORM_OPTIONS)
    for codes in PLATFORM_OPTIONS.values():
        for code in codes:
            if code.endswith(".other"):
                assert code.split(".", 1)[0] in {"appearance"}
