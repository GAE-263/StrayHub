from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from services.api.app.application.adoption_inquiry_service import _resolve_ai_suitability


def _inquiry(**overrides) -> SimpleNamespace:
    defaults = {
        "path": "specific_animal",
        "target_animal_id": uuid4(),
        "ai_suitability_score": None,
        "ai_suitability_explanation": None,
        "match_scores_snapshot": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_specific_animal_uses_its_own_ai_suitability_columns() -> None:
    inquiry = _inquiry(
        path="specific_animal", ai_suitability_score=82, ai_suitability_explanation="很合適"
    )

    score, explanation = _resolve_ai_suitability(inquiry)

    assert score == 82
    assert explanation == "很合適"


def test_specific_animal_shows_no_data_when_ai_never_ran() -> None:
    """No fallback to match_scores_snapshot for this path — that snapshot is
    a rule-based 0-1 score, not the AI's 0-100; showing it here would be a
    misleadingly-scaled number, not an honest "no AI data"."""
    animal_id = uuid4()
    inquiry = _inquiry(
        path="specific_animal",
        target_animal_id=animal_id,
        ai_suitability_score=None,
        match_scores_snapshot=[{"animal_id": str(animal_id), "score": 0.0, "reasons": []}],
    )

    score, explanation = _resolve_ai_suitability(inquiry)

    assert score is None
    assert explanation is None


def test_recommend_me_falls_back_to_the_match_snapshot_for_the_chosen_animal() -> None:
    chosen_id = uuid4()
    other_id = uuid4()
    inquiry = _inquiry(
        path="recommend_me",
        target_animal_id=chosen_id,
        ai_suitability_score=None,
        match_scores_snapshot=[
            {"animal_id": str(other_id), "score": 90, "reasons": ["最推薦的選擇"]},
            {"animal_id": str(chosen_id), "score": 55, "reasons": ["體型合適", "但活動力偏低"]},
        ],
    )

    score, explanation = _resolve_ai_suitability(inquiry)

    assert score == 55
    assert explanation == "體型合適；但活動力偏低"


def test_recommend_me_with_no_snapshot_entry_for_the_chosen_animal_shows_no_data() -> None:
    inquiry = _inquiry(
        path="recommend_me",
        target_animal_id=uuid4(),
        match_scores_snapshot=[{"animal_id": str(uuid4()), "score": 70, "reasons": ["其他理由"]}],
    )

    score, explanation = _resolve_ai_suitability(inquiry)

    assert score is None
    assert explanation is None
