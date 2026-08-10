from scripts.seed_t255_timeline import (
    FIXTURE_SPECS,
    build_fixture_answers,
    stable_id,
)


def test_t255_fixture_covers_required_timeline_states() -> None:
    report_days = [spec.days_ago for spec in FIXTURE_SPECS]

    assert 10 not in report_days
    assert report_days.count(1) == 2
    assert any(spec.days_ago == 7 for spec in FIXTURE_SPECS)
    assert any(spec.days_ago == 4 for spec in FIXTURE_SPECS)
    assert any(spec.ai_job_status == "failed" for spec in FIXTURE_SPECS)


def test_t255_fixture_answers_keep_all_required_questions() -> None:
    for spec in FIXTURE_SPECS:
        answers = build_fixture_answers(spec.answer_overrides)
        assert len(answers) == 13
        assert all(isinstance(value, str) and value for value in answers.values())


def test_t255_fixture_ids_are_stable() -> None:
    from uuid import UUID

    animal_id = UUID("00000000-0000-0000-0000-000000000001")

    assert stable_id("report", "normal-13", animal_id) == stable_id(
        "report", "normal-13", animal_id
    )
    assert stable_id("report", "normal-13", animal_id) != stable_id(
        "report", "normal-12", animal_id
    )
