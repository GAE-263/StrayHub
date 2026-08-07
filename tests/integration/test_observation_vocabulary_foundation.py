from scripts.seed_observation_vocabulary import PLATFORM_OPTIONS


def test_platform_seed_contains_standard_required_vocabulary() -> None:
    required = {
        "care_completion.completed",
        "care_completion.partially_completed",
        "care_completion.not_provided",
        "care_completion.not_observed",
        "care_completion.uncertain",
        "walk_completion.completed",
        "walk_completion.partially_completed",
        "walk_completion.not_done",
        "walk_completion.not_observed",
        "walk_completion.uncertain",
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
    }
    actual = {code for codes in PLATFORM_OPTIONS.values() for code in codes}
    assert required <= actual
    assert set(PLATFORM_OPTIONS["care_completion"]).isdisjoint(PLATFORM_OPTIONS["walk_completion"])
    assert set(PLATFORM_OPTIONS["walk_completion"]).isdisjoint(PLATFORM_OPTIONS["walk"])
