"""Seed deterministic medical-care data for E2E and local quickstart acceptance."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from calendar import monthrange
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from scripts.test_database import require_fixture_database, require_test_database
from services.api.app.domain.care_recurrence import occurrence_id
from services.api.app.domain.organization_timezone import local_to_utc
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.models.medical_care import (
    CareReminderAction,
    CareReminderOccurrence,
    CareReminderSeries,
    MedicalRecord,
)
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.medical_care import NAMESPACE, agenda_occurrence_plan, fixture_uuid

SEED_KEY_PREFIX = "medical-quickstart"
AGENDA_BUCKETS = ("today_pending", "overdue", "today_resolved", "next_seven_days")
PERMISSION_ROLES = (
    "shelter_admin",
    "staff_authorized",
    "staff_denied",
    "volunteer_assigned",
    "volunteer_unassigned",
)


def _database_url() -> str:
    return os.getenv("STRAYHUB_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""


def validate_seed_environment(profile: str, database_url: str | None = None) -> None:
    """Keep every deterministic medical fixture restricted to the local test DB."""
    if profile == "agenda-e2e" and os.getenv("STRAYHUB_MEDICAL_E2E_SEED_ALLOWED") != "1":
        raise RuntimeError("agenda-e2e seed 需要 STRAYHUB_MEDICAL_E2E_SEED_ALLOWED=1")
    if database_url is None:
        require_fixture_database()
    else:
        require_test_database(database_url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("base", "agenda-e2e", "full"), default="full")
    parser.add_argument("--expected-output", type=Path)
    parser.add_argument("--clear", action="store_true")
    return parser


def build_agenda_seed_plan(
    organization_code: str,
    *,
    today: date | None = None,
    count: int = 500,
    timezone_name: str = "Asia/Taipei",
) -> list[dict[str, Any]]:
    """Return deterministic agenda rows whose IDs match the production recurrence domain."""
    source = agenda_occurrence_plan(today=today, count=count)
    resolved_statuses = ("completed", "skipped", "cancelled")
    resolved_index = 0
    plans: list[dict[str, Any]] = []
    for item in source:
        index = int(item["index"])
        lineage_id = uuid5(NAMESPACE, f"seed:{organization_code}:lineage:{index}")
        status = str(item["status"])
        if item["bucket"] == "today_resolved":
            status = resolved_statuses[resolved_index % len(resolved_statuses)]
            resolved_index += 1
        plans.append(
            {
                **item,
                "status": status,
                "series_id": fixture_uuid(f"seed:{organization_code}:series:{index}"),
                "lineage_id": lineage_id,
                "occurrence_id": occurrence_id(lineage_id, 0),
                "animal_index": index % 100,
                "scheduled_local_at": datetime.combine(item["local_date"], item["local_time"])
                .replace(tzinfo=ZoneInfo(timezone_name))
                .isoformat(),
            }
        )
    return plans


def _february_short_month(today: date) -> tuple[date, date, int]:
    year = today.year if today.month >= 2 else today.year - 1
    anchor = date(year, 1, 31)
    nominal = date(year, 2, monthrange(year, 2)[1])
    return anchor, nominal, 1


def _scenario_definitions(today: date) -> list[dict[str, Any]]:
    short_anchor, short_nominal, short_index = _february_short_month(today)
    long_anchor = date(2000, 1, 1)
    return [
        {
            "key": "one-time-pending",
            "title": "Quickstart 情境：今日單次提醒",
            "frequency": "none",
            "interval": 1,
            "anchor_local_date": today,
            "nominal_local_date": today,
            "occurrence_index": 0,
            "end_local_date": None,
            "status": "pending",
            "action_type": None,
            "reminder_type": "medication",
        },
        {
            "key": "long-running-daily",
            "title": "Quickstart 情境：長期每日提醒",
            "frequency": "daily",
            "interval": 1,
            "anchor_local_date": long_anchor,
            "nominal_local_date": today,
            "occurrence_index": (today - long_anchor).days,
            "end_local_date": None,
            "status": "pending",
            "action_type": None,
            "reminder_type": "weight",
        },
        {
            "key": "weekly-completed",
            "title": "Quickstart 情境：每週已完成",
            "frequency": "weekly",
            "interval": 1,
            "anchor_local_date": today - timedelta(days=7),
            "nominal_local_date": today,
            "occurrence_index": 1,
            "end_local_date": None,
            "status": "completed",
            "action_type": "completed",
            "reminder_type": "follow_up",
        },
        {
            "key": "monthly-31-short-month",
            "title": "Quickstart 情境：每月 31 日短月",
            "frequency": "monthly",
            "interval": 1,
            "anchor_local_date": short_anchor,
            "nominal_local_date": short_nominal,
            "occurrence_index": short_index,
            "end_local_date": None,
            "status": "skipped",
            "action_type": "skipped",
            "reminder_type": "vaccination",
        },
        {
            "key": "every-three-months-cancelled",
            "title": "Quickstart 情境：每三個月已取消",
            "frequency": "monthly",
            "interval": 3,
            "anchor_local_date": today,
            "nominal_local_date": today,
            "occurrence_index": 0,
            "end_local_date": None,
            "status": "cancelled",
            "action_type": "cancelled",
            "reminder_type": "examination",
        },
        {
            "key": "yearly-rescheduled",
            "title": "Quickstart 情境：每年已改期",
            "frequency": "yearly",
            "interval": 1,
            "anchor_local_date": today,
            "nominal_local_date": today,
            "occurrence_index": 0,
            "end_local_date": None,
            "status": "pending",
            "action_type": "rescheduled",
            "rescheduled_local_date": today + timedelta(days=3),
            "reminder_type": "vaccination",
        },
        {
            "key": "daily-created-override",
            "title": "Quickstart 情境：每日單次覆寫",
            "frequency": "daily",
            "interval": 1,
            "anchor_local_date": today,
            "nominal_local_date": today,
            "occurrence_index": 0,
            "end_local_date": today + timedelta(days=30),
            "status": "pending",
            "action_type": "created_override",
            "reminder_type": "other",
        },
    ]


def full_profile_definition(*, today: date | None = None) -> dict[str, Any]:
    """Describe all acceptance dimensions populated by the full quickstart profile."""
    local_today = today or datetime.now(ZoneInfo("Asia/Taipei")).date()
    return {
        "organizations": {
            "ORG-A": {"animal_count": 100, "agenda_count": 500},
            "ORG-B": {"animal_count": 20, "agenda_count": 24},
        },
        "permission_roles": PERMISSION_ROLES,
        "scenarios": _scenario_definitions(local_today),
        "timeline_sources": (
            "medical_record",
            "care_report",
            "reminder_action",
            "scheduled_reminder",
        ),
    }


async def _organization(session: AsyncSession, code: str) -> Organization:
    organization = (
        await session.execute(select(Organization).where(Organization.code == code))
    ).scalar_one_or_none()
    if organization is None:
        raise RuntimeError(f"找不到 {code}，請先執行 scripts.seed_test_fixtures")
    organization.timezone = organization.timezone or "Asia/Taipei"
    return organization


async def _ensure_user(
    session: AsyncSession, *, username: str, display_name: str, password_hash: str
) -> User:
    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=fixture_uuid(f"seed:user:{username}"),
            username=username,
            display_name=display_name,
            password_hash=password_hash,
            status="active",
        )
        session.add(user)
        await session.flush()
    else:
        user.display_name = display_name
        user.status = "active"
        if user.password_hash is None:
            user.password_hash = password_hash
    return user


async def _ensure_membership(
    session: AsyncSession,
    *,
    organization: Organization,
    user: User,
    role: str,
    medical_care_access: bool,
    valid_from: datetime | None = None,
    expires_at: datetime | None = None,
) -> OrganizationMembership:
    membership = (
        await session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = OrganizationMembership(
            id=fixture_uuid(f"seed:{organization.code}:membership:{user.username}"),
            organization_id=organization.id,
            user_id=user.id,
            role=role,
            status="active",
            medical_care_access=medical_care_access,
            valid_from=valid_from,
            expires_at=expires_at,
        )
        session.add(membership)
        await session.flush()
    else:
        membership.role = role
        membership.status = "active"
        membership.medical_care_access = medical_care_access
        membership.valid_from = valid_from
        membership.expires_at = expires_at
    return membership


async def _ensure_permission_matrix(
    session: AsyncSession, organization: Organization, now: datetime
) -> dict[str, tuple[User, OrganizationMembership]]:
    suffix = organization.code[-1].lower()
    password_hash = Argon2PasswordHasher().hash("local-only-password")
    definitions = {
        "shelter_admin": (
            "SHELTER_ADMIN",
            True,
            "醫療管理員",
            f"local-shelter-admin-{suffix}",
        ),
        "staff_authorized": ("STAFF", True, "授權醫療工作人員", f"local-staff-{suffix}"),
        "staff_denied": ("STAFF", False, "未授權醫療工作人員", f"medical-staff-denied-{suffix}"),
        "volunteer_assigned": (
            "VOLUNTEER",
            False,
            "被指派照護志工",
            f"local-volunteer-{suffix}",
        ),
        "volunteer_unassigned": (
            "VOLUNTEER",
            False,
            "未被指派志工",
            f"medical-volunteer-unassigned-{suffix}",
        ),
    }
    result: dict[str, tuple[User, OrganizationMembership]] = {}
    for key, (role, access, display_name, username) in definitions.items():
        user = await _ensure_user(
            session,
            username=username,
            display_name=f"{display_name} {organization.code}",
            password_hash=password_hash,
        )
        volunteer = role == "VOLUNTEER"
        membership = await _ensure_membership(
            session,
            organization=organization,
            user=user,
            role=role,
            medical_care_access=access,
            valid_from=now - timedelta(days=30) if volunteer else None,
            expires_at=now + timedelta(days=365) if volunteer else None,
        )
        result[key] = (user, membership)
    return result


async def _ensure_animals(
    session: AsyncSession, organization: Organization, count: int
) -> tuple[list[Animal], Animal]:
    animals: list[Animal] = []
    for index in range(count):
        animal_id = fixture_uuid(f"seed:{organization.code}:animal:{index}")
        animal = await session.get(Animal, animal_id)
        if animal is None:
            animal = Animal(
                id=animal_id,
                organization_id=organization.id,
                name=f"照護動物 {index + 1:03d}",
                shelter_number=f"CARE-{index + 1:03d}",
                status="active",
            )
            session.add(animal)
        else:
            animal.name = f"照護動物 {index + 1:03d}"
            animal.shelter_number = f"CARE-{index + 1:03d}"
            animal.status = "active"
        animals.append(animal)
    inactive_id = fixture_uuid(f"seed:{organization.code}:animal:inactive")
    inactive = await session.get(Animal, inactive_id)
    if inactive is None:
        inactive = Animal(
            id=inactive_id,
            organization_id=organization.id,
            name="已離所照護動物",
            shelter_number="CARE-INACTIVE",
            status="archived",
        )
        session.add(inactive)
    else:
        inactive.status = "archived"
    await session.flush()
    return animals, inactive


async def _ensure_series(
    session: AsyncSession,
    *,
    series_id: UUID,
    lineage_id: UUID,
    organization: Organization,
    animal: Animal,
    actor: User,
    assignee: OrganizationMembership | None,
    title: str,
    reminder_type: str,
    anchor_local_date: date,
    anchor_local_time: time,
    frequency: str,
    interval: int,
    end_local_date: date | None = None,
) -> CareReminderSeries:
    series = await session.get(CareReminderSeries, series_id)
    values = {
        "lineage_id": lineage_id,
        "organization_id": organization.id,
        "animal_id": animal.id,
        "reminder_type": reminder_type,
        "title": title,
        "instructions": "依管理員輸入的照護指示執行；本內容不是系統醫療建議。",
        "assignee_membership_id": assignee.id if assignee else None,
        "anchor_local_date": anchor_local_date,
        "anchor_local_time": anchor_local_time,
        "frequency": frequency,
        "interval": interval,
        "end_local_date": end_local_date,
        "status": "active",
        "created_by_user_id": actor.id,
        "updated_by_user_id": actor.id,
    }
    if series is None:
        series = CareReminderSeries(id=series_id, **values)
        session.add(series)
    else:
        for key, value in values.items():
            setattr(series, key, value)
    await session.flush()
    return series


async def _ensure_occurrence(
    session: AsyncSession,
    *,
    series: CareReminderSeries,
    organization: Organization,
    actor: User,
    occurrence_index: int,
    nominal_local_date: date,
    nominal_local_time: time,
    status: str,
    scheduled_local_date: date | None = None,
) -> CareReminderOccurrence:
    expected_id = occurrence_id(series.lineage_id, occurrence_index)
    occurrence = (
        await session.execute(
            select(CareReminderOccurrence).where(
                CareReminderOccurrence.organization_id == organization.id,
                CareReminderOccurrence.lineage_id == series.lineage_id,
                CareReminderOccurrence.occurrence_index == occurrence_index,
            )
        )
    ).scalar_one_or_none()
    if occurrence is not None and occurrence.id != expected_id:
        await session.execute(
            delete(CareReminderAction).where(CareReminderAction.occurrence_id == occurrence.id)
        )
        await session.delete(occurrence)
        await session.flush()
        occurrence = None
    original_at = local_to_utc(
        datetime.combine(nominal_local_date, nominal_local_time), organization.timezone
    )
    scheduled_at = local_to_utc(
        datetime.combine(scheduled_local_date or nominal_local_date, nominal_local_time),
        organization.timezone,
    )
    acted_at = local_to_utc(
        datetime.combine(datetime.now(ZoneInfo(organization.timezone)).date(), time(10, 30)),
        organization.timezone,
    )
    values = {
        "organization_id": organization.id,
        "lineage_id": series.lineage_id,
        "series_id": series.id,
        "occurrence_index": occurrence_index,
        "nominal_local_date": nominal_local_date,
        "nominal_local_time": nominal_local_time,
        "original_scheduled_at": original_at,
        "scheduled_at": scheduled_at,
        "effective_timezone": organization.timezone,
        "timezone_version": organization.timezone_version,
        "status": status,
        "assignee_membership_id": series.assignee_membership_id,
        "title_snapshot": series.title,
        "instructions_snapshot": series.instructions,
        "type_snapshot": series.reminder_type,
        "last_action_at": acted_at if status != "pending" else None,
        "last_action_by_user_id": actor.id if status != "pending" else None,
        "recorded_at": acted_at if status == "completed" else None,
        "actual_completed_at": acted_at if status == "completed" else None,
        "completed_by_user_id": actor.id if status == "completed" else None,
        "result_note": "Quickstart 已完成" if status == "completed" else None,
    }
    if occurrence is None:
        occurrence = CareReminderOccurrence(id=expected_id, **values)
        session.add(occurrence)
    else:
        for key, value in values.items():
            setattr(occurrence, key, value)
    await session.flush()
    return occurrence


async def _replace_seed_action(
    session: AsyncSession,
    *,
    organization: Organization,
    occurrence: CareReminderOccurrence,
    actor: User,
    action_type: str,
    acted_at: datetime,
) -> CareReminderAction:
    key = f"{SEED_KEY_PREFIX}:{organization.code}:{occurrence.id}:{action_type}"
    action_id = fixture_uuid(f"seed:action:{key}")
    action = await session.get(CareReminderAction, action_id)
    after_status = occurrence.status
    values = {
        "organization_id": organization.id,
        "occurrence_id": occurrence.id,
        "lineage_id": occurrence.lineage_id,
        "series_id": occurrence.series_id,
        "occurrence_index": occurrence.occurrence_index,
        "action_type": action_type,
        "actor_user_id": actor.id,
        "acted_at": acted_at,
        "before_state": {"status": "pending"},
        "after_state": {
            "status": after_status,
            "scheduled_at": occurrence.scheduled_at.isoformat(),
        },
        "reason": "Quickstart 略過原因" if action_type == "skipped" else None,
        "result_note": "Quickstart 執行結果" if action_type == "completed" else None,
        "idempotency_key": key,
        "request_fingerprint": hashlib.sha256(key.encode()).hexdigest(),
    }
    if action is None:
        action = CareReminderAction(id=action_id, **values)
        session.add(action)
    else:
        for field, value in values.items():
            setattr(action, field, value)
    await session.flush()
    return action


def _manifest_item(
    plan: dict[str, Any], organization: Organization, occurrence: CareReminderOccurrence
) -> dict[str, Any]:
    local_at = datetime.combine(
        occurrence.nominal_local_date, occurrence.nominal_local_time
    ).replace(tzinfo=ZoneInfo(organization.timezone))
    return {
        "occurrence_id": str(occurrence.id),
        "series_id": str(occurrence.series_id),
        "lineage_id": str(occurrence.lineage_id),
        "organization_id": str(organization.id),
        "bucket": str(plan["bucket"]),
        "animal_id": str(plan["animal_id"]),
        "animal_name": str(plan["animal_name"]),
        "shelter_number": str(plan["shelter_number"]),
        "reminder_type": str(plan["reminder_type"]),
        "title": str(plan["title"]),
        "local_date": occurrence.nominal_local_date.isoformat(),
        "local_time": occurrence.nominal_local_time.isoformat(),
        "scheduled_local_at": local_at.isoformat(),
        "status": occurrence.status,
    }


def _bucket_manifest(items: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        bucket: {
            "total": sum(item["bucket"] == bucket for item in items),
            "occurrence_ids": [item["occurrence_id"] for item in items if item["bucket"] == bucket],
        }
        for bucket in AGENDA_BUCKETS
    }


async def _seed_agenda(
    session: AsyncSession,
    *,
    organization: Organization,
    actor: User,
    assignee: OrganizationMembership,
    animals: Sequence[Animal],
    count: int,
    today: date,
) -> tuple[list[dict[str, Any]], list[CareReminderAction]]:
    plans = build_agenda_seed_plan(
        organization.code,
        today=today,
        count=count,
        timezone_name=organization.timezone,
    )
    items: list[dict[str, Any]] = []
    actions: list[CareReminderAction] = []
    for plan in plans:
        animal = animals[int(plan["animal_index"]) % len(animals)]
        plan["animal_id"] = animal.id
        plan["animal_name"] = animal.name
        plan["shelter_number"] = animal.shelter_number
        series = await _ensure_series(
            session,
            series_id=plan["series_id"],
            lineage_id=plan["lineage_id"],
            organization=organization,
            animal=animal,
            actor=actor,
            assignee=assignee if int(plan["index"]) % 10 == 0 else None,
            title=str(plan["title"]),
            reminder_type=str(plan["reminder_type"]),
            anchor_local_date=plan["local_date"],
            anchor_local_time=plan["local_time"],
            frequency="none",
            interval=1,
        )
        occurrence = await _ensure_occurrence(
            session,
            series=series,
            organization=organization,
            actor=actor,
            occurrence_index=0,
            nominal_local_date=plan["local_date"],
            nominal_local_time=plan["local_time"],
            status=str(plan["status"]),
        )
        if occurrence.status in {"completed", "skipped", "cancelled"}:
            action = await _replace_seed_action(
                session,
                organization=organization,
                occurrence=occurrence,
                actor=actor,
                action_type=occurrence.status,
                acted_at=occurrence.last_action_at,
            )
            actions.append(action)
        items.append(_manifest_item(plan, organization, occurrence))
    return items, actions


async def _seed_scenarios(
    session: AsyncSession,
    *,
    organization: Organization,
    actor: User,
    assignee: OrganizationMembership,
    animal: Animal,
    today: date,
) -> tuple[list[dict[str, Any]], list[CareReminderAction]]:
    result: list[dict[str, Any]] = []
    actions: list[CareReminderAction] = []
    local_action_at = local_to_utc(datetime.combine(today, time(11, 0)), organization.timezone)
    for scenario in _scenario_definitions(today):
        key = str(scenario["key"])
        series_id = fixture_uuid(f"seed:{organization.code}:scenario-series:{key}")
        lineage_id = fixture_uuid(f"seed:{organization.code}:scenario-lineage:{key}")
        series = await _ensure_series(
            session,
            series_id=series_id,
            lineage_id=lineage_id,
            organization=organization,
            animal=animal,
            actor=actor,
            assignee=assignee,
            title=str(scenario["title"]),
            reminder_type=str(scenario["reminder_type"]),
            anchor_local_date=scenario["anchor_local_date"],
            anchor_local_time=time(8, 30),
            frequency=str(scenario["frequency"]),
            interval=int(scenario["interval"]),
            end_local_date=scenario["end_local_date"],
        )
        occurrence = await _ensure_occurrence(
            session,
            series=series,
            organization=organization,
            actor=actor,
            occurrence_index=int(scenario["occurrence_index"]),
            nominal_local_date=scenario["nominal_local_date"],
            nominal_local_time=time(8, 30),
            status=str(scenario["status"]),
            scheduled_local_date=scenario.get("rescheduled_local_date"),
        )
        action_type = scenario["action_type"]
        action = None
        if action_type:
            action = await _replace_seed_action(
                session,
                organization=organization,
                occurrence=occurrence,
                actor=actor,
                action_type=str(action_type),
                acted_at=local_action_at,
            )
            actions.append(action)
        result.append(
            {
                "key": key,
                "series_id": str(series.id),
                "lineage_id": str(series.lineage_id),
                "occurrence_id": str(occurrence.id),
                "animal_id": str(animal.id),
                "frequency": series.frequency,
                "interval": series.interval,
                "anchor_local_date": series.anchor_local_date.isoformat(),
                "nominal_local_date": occurrence.nominal_local_date.isoformat(),
                "scheduled_at": occurrence.scheduled_at.isoformat(),
                "status": occurrence.status,
                "action_type": action.action_type if action else None,
                "action_id": str(action.id) if action else None,
            }
        )
    return result, actions


async def _seed_timeline(
    session: AsyncSession,
    *,
    organization: Organization,
    actor: User,
    volunteer: User,
    volunteer_membership: OrganizationMembership,
    animal: Animal,
    today: date,
    reminder_actions: Sequence[CareReminderAction],
) -> dict[str, Any]:
    local_times = (time(9, 15), time(9, 45))
    record_ids: list[str] = []
    for index, local_time in enumerate(local_times):
        record_id = fixture_uuid(f"seed:{organization.code}:timeline:medical:{index}")
        record = await session.get(MedicalRecord, record_id)
        values = {
            "organization_id": organization.id,
            "animal_id": animal.id,
            "occurred_at": local_to_utc(datetime.combine(today, local_time), organization.timezone),
            "occurred_timezone": organization.timezone,
            "record_type": "visit" if index == 0 else "weight",
            "title": f"[Quickstart] 同日醫療紀錄 {index + 1}",
            "content": "供 Timeline 多來源驗收使用的自由文字內容。",
            "clinic": "Quickstart 動物醫院" if index == 0 else None,
            "veterinarian": "測試獸醫" if index == 0 else None,
            "weight_kg": 12.5 if index == 1 else None,
            "status": "active",
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        if record is None:
            record = MedicalRecord(id=record_id, **values)
            session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
        record_ids.append(str(record_id))
    report_id = fixture_uuid(f"seed:{organization.code}:timeline:care-report")
    report = await session.get(CareReport, report_id)
    report_values = {
        "organization_id": organization.id,
        "animal_id": animal.id,
        "volunteer_user_id": volunteer.id,
        "membership_id": volunteer_membership.id,
        "answers": {"care_completion": "completed"},
        "answer_snapshots": {"care_completion": {"label": "照護完成", "value": "已完成"}},
        "animal_name_snapshot": animal.name,
        "shelter_number_snapshot": animal.shelter_number,
        "note": "[Quickstart] Timeline 志工日常照護回報",
        "status": "saved",
        "ai_job_status": "not_required",
        "submitted_at": local_to_utc(datetime.combine(today, time(10, 0)), organization.timezone),
    }
    if report is None:
        report = CareReport(id=report_id, **report_values)
        session.add(report)
    else:
        for key, value in report_values.items():
            setattr(report, key, value)
    await session.flush()
    return {
        "animal_id": str(animal.id),
        "medical_record_ids": record_ids,
        "care_report_id": str(report.id),
        "reminder_action_ids": [str(item.id) for item in reminder_actions],
        "sources": [
            "medical_record",
            "care_report",
            "reminder_action",
            "scheduled_reminder",
        ],
    }


async def _seed_organization(
    session: AsyncSession,
    *,
    organization_code: str,
    animal_count: int,
    agenda_count: int,
    today: date,
    include_scenarios: bool,
) -> dict[str, Any]:
    organization = await _organization(session, organization_code)
    now = datetime.now(timezone.utc)
    permissions = await _ensure_permission_matrix(session, organization, now)
    animals, inactive = await _ensure_animals(session, organization, animal_count)
    actor = permissions["shelter_admin"][0]
    assigned_user, assigned_membership = permissions["volunteer_assigned"]
    agenda_items, agenda_actions = await _seed_agenda(
        session,
        organization=organization,
        actor=actor,
        assignee=assigned_membership,
        animals=animals,
        count=agenda_count,
        today=today,
    )
    scenarios: list[dict[str, Any]] = []
    scenario_actions: list[CareReminderAction] = []
    timeline: dict[str, Any] | None = None
    if include_scenarios:
        scenarios, scenario_actions = await _seed_scenarios(
            session,
            organization=organization,
            actor=actor,
            assignee=assigned_membership,
            animal=animals[0],
            today=today,
        )
        timeline = await _seed_timeline(
            session,
            organization=organization,
            actor=actor,
            volunteer=assigned_user,
            volunteer_membership=assigned_membership,
            animal=animals[0],
            today=today,
            reminder_actions=[*agenda_actions, *scenario_actions],
        )
    return {
        "organization_id": str(organization.id),
        "organization_code": organization.code,
        "timezone": organization.timezone,
        "permission_matrix": {
            key: {
                "user_id": str(user.id),
                "membership_id": str(membership.id),
                "username": user.username,
                "role": membership.role,
                "medical_care_access": membership.medical_care_access,
            }
            for key, (user, membership) in permissions.items()
        },
        "active_animal_ids": [str(animal.id) for animal in animals],
        "inactive_animal_id": str(inactive.id),
        "items": agenda_items,
        "buckets": _bucket_manifest(agenda_items),
        "scenarios": scenarios,
        "timeline": timeline,
    }


async def _clear_full_only_artifacts(session: AsyncSession, organization: Organization) -> None:
    """Keep the fixed agenda profile independent from a prior full quickstart run."""
    scenario_series_ids = list(
        (
            await session.execute(
                select(CareReminderSeries.id).where(
                    CareReminderSeries.organization_id == organization.id,
                    CareReminderSeries.title.like("Quickstart 情境：%"),
                )
            )
        ).scalars()
    )
    if scenario_series_ids:
        await session.execute(
            delete(CareReminderAction).where(
                CareReminderAction.organization_id == organization.id,
                CareReminderAction.series_id.in_(scenario_series_ids),
            )
        )
        await session.execute(
            delete(CareReminderOccurrence).where(
                CareReminderOccurrence.organization_id == organization.id,
                CareReminderOccurrence.series_id.in_(scenario_series_ids),
            )
        )
        await session.execute(
            delete(CareReminderSeries).where(
                CareReminderSeries.organization_id == organization.id,
                CareReminderSeries.id.in_(scenario_series_ids),
            )
        )
    await session.execute(
        delete(MedicalRecord).where(
            MedicalRecord.organization_id == organization.id,
            MedicalRecord.title.like("[Quickstart] %"),
        )
    )
    await session.execute(
        delete(CareReport).where(
            CareReport.organization_id == organization.id,
            CareReport.note.like("[Quickstart] %"),
        )
    )


async def seed(profile: str) -> dict[str, Any]:
    validate_seed_environment(profile)
    async with session_factory() as session:
        async with session.begin():
            primary = await _organization(session, "ORG-A")
            local_today = datetime.now(ZoneInfo(primary.timezone)).date()
            if profile == "full":
                definition = full_profile_definition(today=local_today)
                organizations = {
                    code: await _seed_organization(
                        session,
                        organization_code=code,
                        animal_count=int(config["animal_count"]),
                        agenda_count=int(config["agenda_count"]),
                        today=local_today,
                        include_scenarios=True,
                    )
                    for code, config in definition["organizations"].items()
                }
            else:
                count = 500 if profile == "agenda-e2e" else 24
                await _clear_full_only_artifacts(session, primary)
                organizations = {
                    "ORG-A": await _seed_organization(
                        session,
                        organization_code="ORG-A",
                        animal_count=100 if profile == "agenda-e2e" else 10,
                        agenda_count=count,
                        today=local_today,
                        include_scenarios=False,
                    )
                }
    primary_manifest = organizations["ORG-A"]
    result: dict[str, Any] = {
        "profile": profile,
        "generated_for_local_date": local_today.isoformat(),
        "organization_id": primary_manifest["organization_id"],
        "items": primary_manifest["items"],
        "buckets": primary_manifest["buckets"],
    }
    if profile == "full":
        result["organizations"] = organizations
        result["coverage"] = {
            "organization_count": len(organizations),
            "active_animal_count": sum(
                len(item["active_animal_ids"]) for item in organizations.values()
            ),
            "agenda_occurrence_count": sum(len(item["items"]) for item in organizations.values()),
            "permission_roles": list(PERMISSION_ROLES),
            "action_types": sorted(
                {
                    scenario["action_type"]
                    for item in organizations.values()
                    for scenario in item["scenarios"]
                    if scenario["action_type"]
                }
            ),
            "timeline_sources": [
                "medical_record",
                "care_report",
                "reminder_action",
                "scheduled_reminder",
            ],
        }
    return result


async def clear(profile: str) -> None:
    validate_seed_environment(profile)
    organization_codes = ("ORG-A", "ORG-B") if profile == "full" else ("ORG-A",)
    async with session_factory() as session:
        async with session.begin():
            organizations = list(
                (
                    await session.execute(
                        select(Organization).where(Organization.code.in_(organization_codes))
                    )
                ).scalars()
            )
            for organization in organizations:
                series_ids = list(
                    (
                        await session.execute(
                            select(CareReminderSeries.id).where(
                                CareReminderSeries.organization_id == organization.id,
                                or_(
                                    CareReminderSeries.title.like("固定照護事項 %"),
                                    CareReminderSeries.title.like("Quickstart 情境：%"),
                                ),
                            )
                        )
                    ).scalars()
                )
                if series_ids:
                    await session.execute(
                        delete(CareReminderAction).where(
                            CareReminderAction.organization_id == organization.id,
                            CareReminderAction.series_id.in_(series_ids),
                        )
                    )
                    await session.execute(
                        delete(CareReminderOccurrence).where(
                            CareReminderOccurrence.organization_id == organization.id,
                            CareReminderOccurrence.series_id.in_(series_ids),
                        )
                    )
                    await session.execute(
                        delete(CareReminderSeries).where(
                            CareReminderSeries.organization_id == organization.id,
                            CareReminderSeries.id.in_(series_ids),
                        )
                    )
                await session.execute(
                    delete(MedicalRecord).where(
                        MedicalRecord.organization_id == organization.id,
                        MedicalRecord.title.like("[Quickstart] %"),
                    )
                )
                await session.execute(
                    delete(CareReport).where(
                        CareReport.organization_id == organization.id,
                        CareReport.note.like("[Quickstart] %"),
                    )
                )


def main() -> int:
    args = build_parser().parse_args()
    if args.clear:
        asyncio.run(clear(args.profile))
        return 0
    result = asyncio.run(seed(args.profile))
    encoded = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.expected_output:
        args.expected_output.parent.mkdir(parents=True, exist_ok=True)
        args.expected_output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
