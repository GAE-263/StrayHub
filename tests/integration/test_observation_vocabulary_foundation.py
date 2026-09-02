from scripts.seed_observation_vocabulary import OPTION_NAMES, PLATFORM_OPTIONS
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS, UNOBSERVED


def test_platform_seed_is_exact_frozen_walk_vocabulary() -> None:
    assert tuple(PLATFORM_OPTIONS) == REQUIRED_ANSWER_KEYS
    assert PLATFORM_OPTIONS == {
        "walk_completion": (
            "walk_completion.completed",
            "walk_completion.partially_completed",
            "walk_completion.not_done",
        ),
        "activity": ("activity.higher", "activity.usual", "activity.lower"),
        "gait": ("gait.normal", "gait.off", "gait.abnormal"),
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


def test_frozen_traditional_chinese_labels() -> None:
    assert [OPTION_NAMES[code] for code in PLATFORM_OPTIONS["walk_completion"]] == [
        "有走完",
        "走一半",
        "沒走成",
    ]
    assert OPTION_NAMES["animal_interaction.wary"] == "緊張或想衝"
    assert OPTION_NAMES["appearance.none_found"] == "沒發現異狀"


def test_unobserved_is_not_seeded_as_crm_option() -> None:
    assert UNOBSERVED not in {code for codes in PLATFORM_OPTIONS.values() for code in codes}
