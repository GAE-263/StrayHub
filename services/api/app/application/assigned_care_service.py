from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NoReturn
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.application.care_reminder_service import CareReminderService
from services.api.app.domain.care_recurrence import (
    last_index_on_or_before,
    nth_local,
    occurrence_at,
    occurrence_id,
)
from services.api.app.domain.organization_timezone import local_today
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import Organization, OrganizationMembership
from services.api.app.persistence.models.medical_care import (
    CareReminderOccurrence,
    CareReminderSeries,
)
from services.api.app.persistence.repositories.care_reminder_repository import (
    CareReminderRepository,
)


@dataclass(frozen=True)
class AssignedCareAnimal:
    id: UUID
    name: str
    shelter_number: str | None
    photo_url: str | None = None


@dataclass(frozen=True)
class AssignedCareItem:
    occurrence_id: UUID
    version: int
    status: str
    animal: AssignedCareAnimal
    reminder_type: str
    title: str
    instructions: str
    display_local_at: str
    can_complete: bool
    can_skip: bool


@dataclass(frozen=True)
class AssignedCareMutation:
    occurrence: AssignedCareItem
    action_id: UUID
    action_type: str
    acted_at: datetime
    recorded_at: datetime | None
    actual_completed_at: datetime | None


class AssignedCareService:
    def __init__(self, session: AsyncSession, context: RequestContext) -> None:
        self.session = session
        self.context = context
        if context.organization_id is None or context.membership_id is None:
            self._not_found()
        self.organization_id = context.organization_id
        self.membership_id = context.membership_id

    @staticmethod
    def _not_found() -> NoReturn:
        raise DomainError(
            "assigned_care_not_found",
            "指派事項不存在或無法存取",
            404,
        )

    async def _membership(self) -> OrganizationMembership:
        now = datetime.now(timezone.utc)
        membership = (
            await self.session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.id == self.membership_id,
                    OrganizationMembership.organization_id == self.organization_id,
                    OrganizationMembership.user_id == self.context.user_id,
                    OrganizationMembership.role == "VOLUNTEER",
                    OrganizationMembership.status == "active",
                    or_(
                        OrganizationMembership.valid_from.is_(None),
                        OrganizationMembership.valid_from <= now,
                    ),
                    or_(
                        OrganizationMembership.expires_at.is_(None),
                        OrganizationMembership.expires_at > now,
                    ),
                )
            )
        ).scalar_one_or_none()
        if membership is None or self.context.role != "VOLUNTEER":
            self._not_found()
        return membership

    async def _organization(self) -> Organization:
        organization = (
            await self.session.execute(
                select(Organization).where(Organization.id == self.organization_id)
            )
        ).scalar_one_or_none()
        if organization is None or organization.status != "active":
            self._not_found()
        return organization

    async def _animal(self, animal_id: UUID) -> Animal:
        animal = (
            await self.session.execute(
                select(Animal).where(
                    Animal.id == animal_id,
                    Animal.organization_id == self.organization_id,
                )
            )
        ).scalar_one_or_none()
        if animal is None:
            self._not_found()
        return animal

    def _assert_assigned(self, series: CareReminderSeries) -> None:
        if (
            series.organization_id != self.organization_id
            or series.assignee_membership_id != self.membership_id
        ):
            self._not_found()

    @staticmethod
    def _item(
        *,
        series: CareReminderSeries,
        occurrence: CareReminderOccurrence | None,
        occurrence_id_value: UUID,
        scheduled_at: datetime,
        animal: Animal,
        timezone_name: str,
    ) -> AssignedCareItem:
        status = occurrence.status if occurrence is not None else "pending"
        can_act = series.status == "active" and status == "pending"
        return AssignedCareItem(
            occurrence_id=occurrence_id_value,
            version=occurrence.version if occurrence is not None else 0,
            status=status,
            animal=AssignedCareAnimal(
                id=animal.id,
                name=animal.name,
                shelter_number=animal.shelter_number,
            ),
            reminder_type=occurrence.type_snapshot
            if occurrence is not None
            else series.reminder_type,
            title=occurrence.title_snapshot if occurrence is not None else series.title,
            instructions=(
                occurrence.instructions_snapshot if occurrence is not None else series.instructions
            ),
            display_local_at=scheduled_at.astimezone(ZoneInfo(timezone_name)).isoformat(),
            can_complete=can_act,
            can_skip=can_act,
        )

    async def get(self, occurrence_id_value: UUID) -> AssignedCareItem:
        await self._membership()
        organization = await self._organization()
        try:
            series, _, _, scheduled_at = await CareReminderService(
                self.session, self.context
            ).resolve_occurrence(occurrence_id_value)
        except DomainError:
            self._not_found()
        self._assert_assigned(series)
        occurrence = await CareReminderRepository(self.session, self.organization_id).occurrence(
            occurrence_id_value
        )
        animal = await self._animal(series.animal_id)
        return self._item(
            series=series,
            occurrence=occurrence,
            occurrence_id_value=occurrence_id_value,
            scheduled_at=occurrence.scheduled_at if occurrence is not None else scheduled_at,
            animal=animal,
            timezone_name=organization.timezone,
        )

    async def list(self) -> list[AssignedCareItem]:
        await self._membership()
        organization = await self._organization()
        series_rows = list(
            (
                await self.session.execute(
                    select(CareReminderSeries)
                    .where(
                        CareReminderSeries.organization_id == self.organization_id,
                        CareReminderSeries.assignee_membership_id == self.membership_id,
                    )
                    .order_by(CareReminderSeries.anchor_local_date, CareReminderSeries.id)
                )
            ).scalars()
        )
        if not series_rows:
            return []
        occurrences = list(
            (
                await self.session.execute(
                    select(CareReminderOccurrence).where(
                        CareReminderOccurrence.organization_id == self.organization_id,
                        CareReminderOccurrence.series_id.in_([series.id for series in series_rows]),
                    )
                )
            ).scalars()
        )
        by_series: dict[UUID, list[CareReminderOccurrence]] = {}
        for occurrence in occurrences:
            by_series.setdefault(occurrence.series_id, []).append(occurrence)
        animal_ids = {series.animal_id for series in series_rows}
        animals = {
            animal.id: animal
            for animal in (
                await self.session.execute(
                    select(Animal).where(
                        Animal.organization_id == self.organization_id,
                        Animal.id.in_(animal_ids),
                    )
                )
            ).scalars()
        }
        items: dict[UUID, tuple[datetime, AssignedCareItem]] = {}
        today = local_today(organization.timezone)
        for series in series_rows:
            animal = animals.get(series.animal_id)
            if animal is None:
                continue
            for occurrence in by_series.get(series.id, []):
                items[occurrence.id] = (
                    occurrence.scheduled_at,
                    self._item(
                        series=series,
                        occurrence=occurrence,
                        occurrence_id_value=occurrence.id,
                        scheduled_at=occurrence.scheduled_at,
                        animal=animal,
                        timezone_name=organization.timezone,
                    ),
                )
            if series.status != "active":
                continue
            index = last_index_on_or_before(
                series.anchor_local_date,
                series.frequency,
                series.interval,
                today,
            )
            if index is None:
                index = series.start_ordinal
            index = max(index, series.start_ordinal)
            if series.end_ordinal is not None and index > series.end_ordinal:
                continue
            nominal_day = nth_local(
                series.anchor_local_date,
                series.frequency,
                series.interval,
                index,
            )
            if series.end_local_date is not None and nominal_day > series.end_local_date:
                continue
            oid = occurrence_id(series.lineage_id, index)
            if oid in items:
                continue
            scheduled_at = occurrence_at(
                series.anchor_local_date,
                series.anchor_local_time,
                series.frequency,
                series.interval,
                index,
                organization.timezone,
            )
            items[oid] = (
                scheduled_at,
                self._item(
                    series=series,
                    occurrence=None,
                    occurrence_id_value=oid,
                    scheduled_at=scheduled_at,
                    animal=animal,
                    timezone_name=organization.timezone,
                ),
            )
        return [item for _, item in sorted(items.values(), key=lambda value: value[0])]

    async def act(
        self,
        occurrence_id_value: UUID,
        *,
        action: str,
        expected_version: int,
        reason: str | None,
        result_note: str | None,
        actual_completed_at: datetime | None,
        idempotency_key: str,
    ) -> AssignedCareMutation:
        await self._membership()
        organization = await self._organization()
        try:
            series, _, _, scheduled_at = await CareReminderService(
                self.session, self.context
            ).resolve_occurrence(occurrence_id_value)
        except DomainError:
            self._not_found()
        locked_series = await CareReminderRepository(self.session, self.organization_id).series(
            series.id, for_update=True
        )
        if locked_series is None:
            self._not_found()
        self._assert_assigned(locked_series)
        if locked_series.status != "active":
            self._not_found()
        animal = await self._animal(locked_series.animal_id)
        normalized_action = {
            "complete": "completed",
            "completed": "completed",
            "skip": "skipped",
            "skipped": "skipped",
        }.get(action)
        if normalized_action is None:
            raise DomainError("assigned_care_action_invalid", "志工只能完成或略過指派事項", 422)
        result = await CareReminderService(self.session, self.context).act(
            occurrence_id_value,
            normalized_action,
            reason,
            result_note,
            idempotency_key,
            {"actual_completed_at": actual_completed_at},
            expected_version,
        )
        occurrence = result.occurrence
        item = self._item(
            series=locked_series,
            occurrence=occurrence,
            occurrence_id_value=occurrence.id,
            scheduled_at=occurrence.scheduled_at if occurrence is not None else scheduled_at,
            animal=animal,
            timezone_name=organization.timezone,
        )
        return AssignedCareMutation(
            occurrence=item,
            action_id=result.action.id,
            action_type=result.action.action_type,
            acted_at=result.action.acted_at,
            recorded_at=occurrence.recorded_at,
            actual_completed_at=occurrence.actual_completed_at,
        )
