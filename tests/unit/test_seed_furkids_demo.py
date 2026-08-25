from scripts.seed_furkids_demo import (
    ANIMAL_SPECS,
    CARE_REPORT_COUNTS,
    ORGANIZATION_CODE,
    ORGANIZATION_NAME,
    build_seed_plan,
)


def test_furkids_seed_plan_has_fixed_organization_and_animals() -> None:
    plan = build_seed_plan()

    assert ORGANIZATION_CODE == "FURKIDS-ASIA"
    assert ORGANIZATION_NAME == "毛小孩幸福聯盟協會"
    assert [animal.name for animal in ANIMAL_SPECS] == [
        "獒黃妹",
        "獒一搓",
        "獒瓦蛤",
        "獒凱西",
        "柴福福",
    ]
    assert [animal.shelter_number for animal in ANIMAL_SPECS] == [
        "MTF-20140531-001",
        "MTF-20241213-001",
        "MTF-20240515-001",
        "MTF-20200605-001",
        "SBA-20170922-001",
    ]
    assert plan["organization"]["timezone"] == "Asia/Taipei"


def test_furkids_seed_plan_separates_source_facts_from_synthetic_data() -> None:
    plan = build_seed_plan()

    assert plan["source_derived"]["獒一搓"]["sex"] == "公犬"
    assert plan["source_derived"]["柴福福"]["intake_date"] == "2017-09-22"
    assert sum(CARE_REPORT_COUNTS.values()) == 20
    assert plan["synthetic_counts"] == {
        "medical_records": 8,
        "care_reminders": 3,
        "care_reports": 20,
    }
    assert "DailyReportableScope" not in plan["persistence_models"]


def test_furkids_seed_identifiers_are_unique_and_repeatable() -> None:
    first = build_seed_plan()
    second = build_seed_plan()

    assert first == second
    assert len({animal.id for animal in ANIMAL_SPECS}) == 5
    assert len({animal.shelter_number for animal in ANIMAL_SPECS}) == 5
