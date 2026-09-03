"""Pure cadence decision for 毛孩日記's periodic LINE push reminder — no I/O,
no LINE/DB access, just "given these timestamps, is a reminder due now?" so
it can be unit-tested without a worker or a database.

Cadence (per user decision): weekly for the first ~3 months after adoption
(the period adopters most need encouragement/check-ins), then monthly once
the pet has settled in."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

EARLY_PHASE_DURATION_DAYS = 90
EARLY_PHASE_CADENCE_DAYS = 7
STABLE_PHASE_CADENCE_DAYS = 30


class GrowthDiaryPhase:
    EARLY = "early"
    STABLE = "stable"


@dataclass(frozen=True)
class GrowthDiaryReminderDecision:
    phase: str
    cadence_days: int
    due: bool


def decide_growth_diary_reminder(
    *,
    adopted_at: datetime,
    last_prompted_at: datetime | None,
    now: datetime,
) -> GrowthDiaryReminderDecision:
    """`last_prompted_at` is the later of "last reminder pushed" and "last
    entry submitted" (see AdoptionInquiry.last_growth_diary_prompted_at) —
    either resets the cadence clock, so a reminder never fires right after
    the adopter already shared an update on their own. `None` means neither
    has ever happened, so the clock starts at the adoption date itself."""
    days_since_adoption = (now - adopted_at).days
    if days_since_adoption < EARLY_PHASE_DURATION_DAYS:
        phase = GrowthDiaryPhase.EARLY
        cadence_days = EARLY_PHASE_CADENCE_DAYS
    else:
        phase = GrowthDiaryPhase.STABLE
        cadence_days = STABLE_PHASE_CADENCE_DAYS
    anchor = last_prompted_at or adopted_at
    due = (now - anchor) >= timedelta(days=cadence_days)
    return GrowthDiaryReminderDecision(phase=phase, cadence_days=cadence_days, due=due)
