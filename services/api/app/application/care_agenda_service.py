# ruff: noqa: E501
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.application.medical_care_common import medical_permission
from services.api.app.domain.care_recurrence import nth_local, occurrence_at, occurrence_id
from services.api.app.domain.medical_care_access import require_medical_view
from services.api.app.domain.organization_timezone import local_today
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.models.medical_care import (
    CareReminderOccurrence,
)
from services.api.app.persistence.repositories.care_reminder_repository import (
    CareReminderRepository,
)


@dataclass(frozen=True)
class AgendaItem:
    occurrence_id: UUID
    animal_id: UUID
    animal_name: str
    shelter_number: str | None
    reminder_type: str
    title: str
    instructions: str
    scheduled_at: datetime
    status: str
    version: int
    is_virtual: bool
    assignee_membership_id: UUID | None

    def as_dict(self) -> dict[str, object]:
        return {
            "occurrence_id": str(self.occurrence_id),
            "animal_id": str(self.animal_id),
            "animal_name": self.animal_name,
            "shelter_number": self.shelter_number,
            "reminder_type": self.reminder_type,
            "title": self.title,
            "instructions": self.instructions,
            "scheduled_at": self.scheduled_at.isoformat(),
            "status": self.status,
            "version": self.version,
            "is_virtual": self.is_virtual,
            "assignee_membership_id": str(self.assignee_membership_id)
            if self.assignee_membership_id
            else None,
        }


class CareAgendaService:
    def __init__(self, session: AsyncSession, context: RequestContext) -> None:
        self.session = session
        self.context = context
        if context.organization_id is None:
            raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
        self.organization_id = context.organization_id

    async def build(
        self,
        *,
        target_day: date | None = None,
        animal_id: UUID | None = None,
        reminder_type: str | None = None,
        assignee_membership_id: UUID | None = None,
        status_filter: str | None = None,
        page_size: int = 50,
        cursors: dict[str, int] | None = None,
    ) -> dict[str, object]:
        permission = await medical_permission(self.session, self.context)
        require_medical_view(permission)
        organization = (
            await self.session.execute(
                select(Organization).where(Organization.id == self.organization_id)
            )
        ).scalar_one_or_none()
        if organization is None:
            raise DomainError("organization_not_found", "收容所不存在", 404)
        today = target_day or local_today(organization.timezone)
        persisted = {
            item.id: item
            for item in (
                await self.session.execute(
                    select(CareReminderOccurrence).where(
                        CareReminderOccurrence.organization_id == self.organization_id
                    )
                )
            ).scalars()
        }
        animal_query = select(Animal).where(Animal.organization_id == self.organization_id)
        if animal_id is not None:
            animal_query = animal_query.where(Animal.id == animal_id)
        animals = {item.id: item for item in (await self.session.execute(animal_query)).scalars()}
        repo = CareReminderRepository(self.session, self.organization_id)
        buckets: dict[str, list[AgendaItem]] = {
            "today_pending": [],
            "overdue": [],
            "today_resolved": [],
            "next_seven_days": [],
        }
        # Keep the source bounded for future buckets, while overdue walks from ordinal 0
        # so a long-running daily series is never silently truncated.
        for series in await repo.list_series(animal_id):
            if series.status != "active":
                continue
            if reminder_type and series.reminder_type != reminder_type:
                continue
            if (
                assignee_membership_id is not None
                and series.assignee_membership_id != assignee_membership_id
            ):
                continue
            animal = animals.get(series.animal_id)
            if animal is None:
                continue
            upper = max(0, (today - series.anchor_local_date).days + 7) + 1
            for index in range(series.start_ordinal, upper):
                if series.end_ordinal is not None and index > series.end_ordinal:
                    break
                nominal = nth_local(
                    series.anchor_local_date, series.frequency, series.interval, index
                )
                if series.frequency == "none" and index > series.start_ordinal:
                    break
                if series.end_local_date and nominal > series.end_local_date:
                    break
                if nominal > today + timedelta(days=7):
                    break
                oid = occurrence_id(series.lineage_id, index)
                occurrence = persisted.get(oid)
                state = occurrence.status if occurrence else "pending"
                scheduled = (
                    occurrence.scheduled_at
                    if occurrence
                    else occurrence_at(
                        series.anchor_local_date,
                        series.anchor_local_time,
                        series.frequency,
                        series.interval,
                        index,
                        organization.timezone,
                    )
                )
                item = AgendaItem(
                    occurrence_id=oid,
                    animal_id=animal.id,
                    animal_name=animal.name,
                    shelter_number=animal.shelter_number,
                    reminder_type=occurrence.type_snapshot if occurrence else series.reminder_type,
                    title=occurrence.title_snapshot if occurrence else series.title,
                    instructions=occurrence.instructions_snapshot
                    if occurrence
                    else series.instructions,
                    scheduled_at=scheduled,
                    status=state,
                    version=occurrence.version if occurrence else 0,
                    is_virtual=occurrence is None,
                    assignee_membership_id=series.assignee_membership_id,
                )
                local_scheduled_date = scheduled.astimezone(ZoneInfo(organization.timezone)).date()
                bucket: str | None = None
                if state == "pending" and local_scheduled_date < today:
                    bucket = "overdue"
                elif state == "pending" and local_scheduled_date == today:
                    bucket = "today_pending"
                elif (
                    state in {"completed", "skipped", "cancelled"}
                    and occurrence is not None
                    and occurrence.last_action_at is not None
                    and local_today(organization.timezone, occurrence.last_action_at) == today
                ):
                    bucket = "today_resolved"
                elif state == "pending" and today < local_scheduled_date <= today + timedelta(
                    days=7
                ):
                    bucket = "next_seven_days"
                if bucket is not None and (status_filter is None or status_filter == state):
                    buckets[bucket].append(item)
        for values in buckets.values():
            values.sort(key=lambda item: (item.scheduled_at, str(item.occurrence_id)))
        cursors = cursors or {}
        response_buckets: dict[str, dict[str, object]] = {}
        for name, values in buckets.items():
            offset = max(0, cursors.get(name, 0))
            page = values[offset : offset + page_size]
            response_buckets[name] = {
                "items": [item.as_dict() for item in page],
                "total_count": len(values),
                "next_cursor": str(offset + len(page))
                if offset + len(page) < len(values)
                else None,
            }
        totals = {name: bucket["total_count"] for name, bucket in response_buckets.items()}
        if totals["overdue"]:
            today_state = "overdue"
        elif totals["today_pending"]:
            today_state = "pending"
        elif totals["today_resolved"]:
            today_state = "events_no_todos"
        else:
            today_state = "no_activity"
        return {
            "local_today": today.isoformat(),
            "today_state": today_state,
            "organization_timezone": organization.timezone,
            "timezone": organization.timezone,
            "timezone_version": organization.timezone_version,
            "filters": {
                "animal_id": str(animal_id) if animal_id else None,
                "reminder_type": reminder_type,
                "assignee_membership_id": str(assignee_membership_id)
                if assignee_membership_id
                else None,
                "status": status_filter,
            },
            "pages": response_buckets,
            **response_buckets,
            "buckets": {name: bucket["items"] for name, bucket in response_buckets.items()},
            "totals": totals,
        }

    async def calendar(
        self,
        *,
        date_from: date,
        date_to: date,
        animal_id: UUID | None = None,
        reminder_type: str | None = None,
    ) -> dict[str, object]:
        if date_to < date_from or (date_to - date_from).days > 366:
            raise DomainError("calendar_range_invalid", "行事曆查詢範圍最多 366 天", 422)
        agendas = [
            await self.build(
                target_day=date_from + timedelta(days=offset),
                animal_id=animal_id,
                reminder_type=reminder_type,
                page_size=100,
            )
            for offset in range((date_to - date_from).days + 1)
        ]
        agenda = agendas[0]
        seen: set[str] = set()
        items: list[dict[str, object]] = []
        for day_agenda in agendas:
            for bucket in ("today_pending", "overdue", "today_resolved", "next_seven_days"):
                bucket_data = cast(dict[str, object], day_agenda[bucket])
                for item in cast(list[dict[str, object]], bucket_data["items"]):
                    if str(item["occurrence_id"]) not in seen:
                        seen.add(str(item["occurrence_id"]))
                        items.append(item)
        days: dict[str, list[dict[str, object]]] = {}
        for item in items:
            local_date = datetime.fromisoformat(str(item["scheduled_at"])).date().isoformat()
            if date_from.isoformat() <= local_date <= date_to.isoformat():
                days.setdefault(local_date, []).append(item)
        return {
            "organization_timezone": agenda["organization_timezone"],
            "timezone_version": agenda["timezone_version"],
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "days": [{"local_date": key, "items": value} for key, value in sorted(days.items())],
            "total_count": sum(len(value) for value in days.values()),
            "next_cursor": None,
        }
