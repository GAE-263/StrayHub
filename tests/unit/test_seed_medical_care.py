from __future__ import annotations

from datetime import date

import pytest
from scripts.seed_medical_care import (
    build_agenda_seed_plan,
    build_parser,
    full_profile_definition,
    validate_seed_environment,
)
from services.api.app.domain.care_recurrence import occurrence_id


def test_cli_defaults_to_full_profile() -> None:
    assert build_parser().parse_args([]).profile == "full"


def test_agenda_e2e_keeps_opt_in_and_loopback_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRAYHUB_MEDICAL_E2E_SEED_ALLOWED", raising=False)
    with pytest.raises(RuntimeError, match="STRAYHUB_MEDICAL_E2E_SEED_ALLOWED=1"):
        validate_seed_environment(
            "agenda-e2e", "postgresql://strayhub:test@127.0.0.1:65432/strayhub_test"
        )

    monkeypatch.setenv("STRAYHUB_MEDICAL_E2E_SEED_ALLOWED", "1")
    with pytest.raises(RuntimeError, match="not an approved local test target"):
        validate_seed_environment(
            "agenda-e2e", "postgresql://strayhub:test@database.example/strayhub_test"
        )
    validate_seed_environment(
        "agenda-e2e", "postgresql://strayhub:test@localhost:65432/strayhub_test"
    )


def test_agenda_plan_uses_domain_occurrence_ids_and_exact_bucket_totals() -> None:
    plans = build_agenda_seed_plan("ORG-A", today=date(2026, 2, 28), count=500)

    assert len(plans) == 500
    assert len({item["occurrence_id"] for item in plans}) == 500
    assert all(item["occurrence_id"] == occurrence_id(item["lineage_id"], 0) for item in plans)
    assert {
        bucket: sum(item["bucket"] == bucket for item in plans)
        for bucket in ("today_pending", "overdue", "today_resolved", "next_seven_days")
    } == {
        "today_pending": 125,
        "overdue": 125,
        "today_resolved": 125,
        "next_seven_days": 125,
    }
    assert {item["status"] for item in plans if item["bucket"] == "today_resolved"} == {
        "completed",
        "skipped",
        "cancelled",
    }
    assert all(
        {
            "occurrence_id",
            "series_id",
            "lineage_id",
            "bucket",
            "animal_name",
            "shelter_number",
            "reminder_type",
            "title",
            "scheduled_local_at",
            "status",
        }
        <= item.keys()
        for item in plans
    )
    assert plans[0]["scheduled_local_at"] == "2026-02-28T09:00:00+08:00"


def test_two_shelters_share_visible_fixture_shape_but_not_internal_ids() -> None:
    org_a = build_agenda_seed_plan("ORG-A", today=date(2026, 8, 16), count=1)[0]
    org_b = build_agenda_seed_plan("ORG-B", today=date(2026, 8, 16), count=1)[0]

    for field in (
        "animal_name",
        "shelter_number",
        "reminder_type",
        "title",
        "scheduled_local_at",
        "status",
    ):
        assert org_a[field] == org_b[field]
    assert org_a["series_id"] != org_b["series_id"]
    assert org_a["lineage_id"] != org_b["lineage_id"]
    assert org_a["occurrence_id"] != org_b["occurrence_id"]


def test_full_profile_covers_delivery_and_safety_acceptance_data() -> None:
    definition = full_profile_definition(today=date(2026, 2, 28))

    assert set(definition["organizations"]) == {"ORG-A", "ORG-B"}
    assert definition["organizations"]["ORG-A"]["animal_count"] >= 100
    assert definition["organizations"]["ORG-A"]["agenda_count"] >= 500
    assert set(definition["permission_roles"]) == {
        "shelter_admin",
        "staff_authorized",
        "staff_denied",
        "volunteer_assigned",
        "volunteer_unassigned",
    }
    scenarios = definition["scenarios"]
    assert {item["frequency"] for item in scenarios} >= {
        "none",
        "daily",
        "weekly",
        "monthly",
        "yearly",
    }
    assert any(
        item["frequency"] == "monthly"
        and item["interval"] == 1
        and item["anchor_local_date"].day == 31
        and item["nominal_local_date"] == date(2026, 2, 28)
        for item in scenarios
    )
    assert any(item["frequency"] == "monthly" and item["interval"] == 3 for item in scenarios)
    assert any(
        item["frequency"] == "daily"
        and item["anchor_local_date"] == date(2000, 1, 1)
        and item["end_local_date"] is None
        for item in scenarios
    )
    assert {item["action_type"] for item in scenarios if item["action_type"]} >= {
        "created_override",
        "completed",
        "skipped",
        "cancelled",
        "rescheduled",
    }
    assert set(definition["timeline_sources"]) == {
        "medical_record",
        "care_report",
        "reminder_action",
        "scheduled_reminder",
    }
