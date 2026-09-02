from datetime import datetime, timedelta, timezone

from services.api.app.domain.growth_diary_reminder import (
    EARLY_PHASE_CADENCE_DAYS,
    EARLY_PHASE_DURATION_DAYS,
    STABLE_PHASE_CADENCE_DAYS,
    GrowthDiaryPhase,
    decide_growth_diary_reminder,
)

_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_early_phase_uses_weekly_cadence_from_adoption_date() -> None:
    adopted_at = _NOW - timedelta(days=10)
    decision = decide_growth_diary_reminder(adopted_at=adopted_at, last_prompted_at=None, now=_NOW)
    assert decision.phase == GrowthDiaryPhase.EARLY
    assert decision.cadence_days == EARLY_PHASE_CADENCE_DAYS
    assert decision.due is True


def test_early_phase_not_due_before_a_week_since_last_prompt() -> None:
    adopted_at = _NOW - timedelta(days=10)
    last_prompted_at = _NOW - timedelta(days=3)
    decision = decide_growth_diary_reminder(
        adopted_at=adopted_at, last_prompted_at=last_prompted_at, now=_NOW
    )
    assert decision.phase == GrowthDiaryPhase.EARLY
    assert decision.due is False


def test_adopter_sharing_on_their_own_resets_the_clock() -> None:
    """`last_prompted_at` is "later of reminder pushed / entry submitted" —
    an adopter who shares unprompted must not get re-pinged immediately."""
    adopted_at = _NOW - timedelta(days=60)
    last_prompted_at = _NOW - timedelta(hours=1)
    decision = decide_growth_diary_reminder(
        adopted_at=adopted_at, last_prompted_at=last_prompted_at, now=_NOW
    )
    assert decision.due is False


def test_stable_phase_after_three_months_uses_monthly_cadence() -> None:
    adopted_at = _NOW - timedelta(days=EARLY_PHASE_DURATION_DAYS + 5)
    last_prompted_at = _NOW - timedelta(days=STABLE_PHASE_CADENCE_DAYS)
    decision = decide_growth_diary_reminder(
        adopted_at=adopted_at, last_prompted_at=last_prompted_at, now=_NOW
    )
    assert decision.phase == GrowthDiaryPhase.STABLE
    assert decision.cadence_days == STABLE_PHASE_CADENCE_DAYS
    assert decision.due is True


def test_stable_phase_not_due_after_only_one_week() -> None:
    adopted_at = _NOW - timedelta(days=EARLY_PHASE_DURATION_DAYS + 5)
    last_prompted_at = _NOW - timedelta(days=EARLY_PHASE_CADENCE_DAYS)
    decision = decide_growth_diary_reminder(
        adopted_at=adopted_at, last_prompted_at=last_prompted_at, now=_NOW
    )
    assert decision.phase == GrowthDiaryPhase.STABLE
    assert decision.due is False


def test_phase_boundary_is_exactly_the_duration_constant() -> None:
    adopted_at = _NOW - timedelta(days=EARLY_PHASE_DURATION_DAYS)
    decision = decide_growth_diary_reminder(adopted_at=adopted_at, last_prompted_at=None, now=_NOW)
    assert decision.phase == GrowthDiaryPhase.STABLE
