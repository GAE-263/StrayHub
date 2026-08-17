"""Deterministic medical-care fixture builders used by integration and E2E tests."""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid5

NAMESPACE = UUID("7b22e692-31aa-4e54-a65e-68efdc431006")


def fixture_uuid(label: str) -> UUID:
    return uuid5(NAMESPACE, label)


@dataclass(frozen=True)
class MedicalCareFixture:
    organization_id: UUID
    user_ids: dict[str, UUID]
    membership_ids: dict[str, UUID]
    animal_ids: tuple[UUID, ...]
    series_ids: tuple[UUID, ...]
    occurrence_ids: tuple[UUID, ...]


def build_fixture(*, organization_key: str = "ORG-A", animal_count: int = 5) -> MedicalCareFixture:
    """Return stable IDs without touching a database."""
    prefix = organization_key.lower()
    return MedicalCareFixture(
        organization_id=fixture_uuid(f"organization:{prefix}"),
        user_ids={
            role: fixture_uuid(f"user:{prefix}:{role}")
            for role in (
                "admin",
                "staff_authorized",
                "staff_denied",
                "volunteer",
                "other_volunteer",
            )
        },
        membership_ids={
            role: fixture_uuid(f"membership:{prefix}:{role}")
            for role in (
                "admin",
                "staff_authorized",
                "staff_denied",
                "volunteer",
                "other_volunteer",
            )
        },
        animal_ids=tuple(fixture_uuid(f"animal:{prefix}:{index}") for index in range(animal_count)),
        series_ids=tuple(fixture_uuid(f"series:{prefix}:{index}") for index in range(animal_count)),
        occurrence_ids=tuple(
            fixture_uuid(f"occurrence:{prefix}:{index}") for index in range(animal_count)
        ),
    )


def build_fixture_matrix(*, animal_count: int = 5) -> dict[str, MedicalCareFixture]:
    """Return the same deterministic fixture shape for two isolated shelters."""
    return {
        organization_key: build_fixture(
            organization_key=organization_key, animal_count=animal_count
        )
        for organization_key in ("ORG-A", "ORG-B")
    }


def agenda_occurrence_plan(
    *, today: date | None = None, count: int = 500
) -> list[dict[str, object]]:
    """Build a repeatable mixed bucket plan for 100/500 Agenda fixtures."""
    day = today or datetime.now(timezone.utc).date()
    plans: list[dict[str, object]] = []
    buckets = ("today_pending", "overdue", "today_resolved", "next_seven_days")
    for index in range(count):
        bucket = buckets[index % len(buckets)]
        offset = {"today_pending": 0, "overdue": -1, "today_resolved": 0, "next_seven_days": 1}[
            bucket
        ]
        status = (
            "pending"
            if bucket in {"today_pending", "overdue", "next_seven_days"}
            else ("completed" if index % 3 == 0 else "skipped")
        )
        plans.append(
            {
                "index": index,
                "bucket": bucket,
                "local_date": day + timedelta(days=offset),
                "local_time": time(9, index % 60),
                "status": status,
                "occurrence_id": fixture_uuid(f"agenda:occurrence:{index}"),
                "animal_name": f"照護動物 {index % 100 + 1:03d}",
                "shelter_number": f"CARE-{index % 100 + 1:03d}",
                "reminder_type": ("medication", "follow_up", "weight", "vaccination")[index % 4],
                "title": f"固定照護事項 {index + 1}",
            }
        )
    return plans
