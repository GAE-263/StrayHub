import json

import pytest
from scripts.experiment_report_summary import sample
from services.api.app.domain.report_summary import fingerprint, rule_summary, validate_summary


def output(**changes):
    return json.dumps(
        {
            "attention_level": "normal",
            "summary": "志工回報散步完成。",
            "evidence": [],
            "uncertainties": [],
            "information_quality": "clear",
            **changes,
        }
    )


def test_rule_floor_and_unobserved_are_not_healthy():
    report = sample({"gait": "gait.abnormal", "activity": "unobserved"})
    result = validate_summary(output(), report)
    assert result["attention_level"] == "urgent"
    assert result["information_quality"] == "insufficient"
    assert {"field": "gait", "quote": "明顯不對"} in result["evidence"]


def test_keyword_does_not_override_negation():
    report = sample(note="今天沒有流血，也沒有跛腳。")
    assert rule_summary(report)["attention_level"] == "normal"


@pytest.mark.parametrize(
    "raw",
    [
        '{"score": 100}',
        output(evidence=[{"field": "note", "quote": "右腳流血"}]),
        output(attention_level="urgent"),
        output(health_score=98),
        output(summary=42),
    ],
)
def test_rejects_invalid_or_ungrounded_output(raw):
    with pytest.raises(ValueError):
        validate_summary(raw, sample(note="散步正常"))


def test_fingerprint_changes_on_correction_and_uses_matching_snapshot_only():
    report = sample()
    before = fingerprint(report)
    report.answer_snapshots = {"gait": {"code": "gait.normal", "display_name": "正常"}}
    report.answers["gait"] = "gait.abnormal"
    assert fingerprint(report) != before
    assert rule_summary(report)["evidence"] == [{"field": "gait", "quote": "明顯不對"}]
