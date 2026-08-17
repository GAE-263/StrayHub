from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.medical_care import (
    CareReminderAction,
    CareReminderOccurrence,
    CareReminderSeries,
)


class CareReminderRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session, self.organization_id = session, organization_id

    async def series(
        self, series_id: UUID, *, for_update: bool = False
    ) -> CareReminderSeries | None:
        query = select(CareReminderSeries).where(
            CareReminderSeries.id == series_id,
            CareReminderSeries.organization_id == self.organization_id,
        )
        if for_update:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def list_series(self, animal_id: UUID | None = None) -> list[CareReminderSeries]:
        query = select(CareReminderSeries).where(
            CareReminderSeries.organization_id == self.organization_id
        )
        if animal_id:
            query = query.where(CareReminderSeries.animal_id == animal_id)
        return list(
            (
                await self.session.execute(
                    query.order_by(CareReminderSeries.anchor_local_date, CareReminderSeries.id)
                )
            ).scalars()
        )

    async def active_series(
        self,
        *,
        animal_id: UUID | None = None,
        assignee_membership_id: UUID | None = None,
    ) -> list[CareReminderSeries]:
        query = select(CareReminderSeries).where(
            CareReminderSeries.organization_id == self.organization_id,
            CareReminderSeries.status == "active",
        )
        if animal_id is not None:
            query = query.where(CareReminderSeries.animal_id == animal_id)
        if assignee_membership_id is not None:
            query = query.where(CareReminderSeries.assignee_membership_id == assignee_membership_id)
        return list(
            (
                await self.session.execute(
                    query.order_by(CareReminderSeries.anchor_local_date, CareReminderSeries.id)
                )
            ).scalars()
        )

    async def occurrences_for_series(
        self, series_ids: list[UUID], *, for_update: bool = False
    ) -> list[CareReminderOccurrence]:
        if not series_ids:
            return []
        query = select(CareReminderOccurrence).where(
            CareReminderOccurrence.organization_id == self.organization_id,
            CareReminderOccurrence.series_id.in_(series_ids),
        )
        if for_update:
            query = query.with_for_update()
        return list((await self.session.execute(query)).scalars())

    async def actions_for_occurrence(self, occurrence_id: UUID) -> list[CareReminderAction]:
        return list(
            (
                await self.session.execute(
                    select(CareReminderAction)
                    .where(
                        CareReminderAction.organization_id == self.organization_id,
                        CareReminderAction.occurrence_id == occurrence_id,
                    )
                    .order_by(CareReminderAction.acted_at, CareReminderAction.id)
                )
            ).scalars()
        )

    async def occurrence(
        self, occurrence_id: UUID, *, for_update: bool = False
    ) -> CareReminderOccurrence | None:
        query = select(CareReminderOccurrence).where(
            CareReminderOccurrence.id == occurrence_id,
            CareReminderOccurrence.organization_id == self.organization_id,
        )
        if for_update:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def action_by_idempotency(
        self, *, actor_user_id: UUID, idempotency_key: str
    ) -> CareReminderAction | None:
        return (
            await self.session.execute(
                select(CareReminderAction).where(
                    CareReminderAction.organization_id == self.organization_id,
                    CareReminderAction.actor_user_id == actor_user_id,
                    CareReminderAction.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    async def add_occurrence_race_safe(
        self, occurrence: CareReminderOccurrence
    ) -> tuple[CareReminderOccurrence, bool]:
        try:
            async with self.session.begin_nested():
                self.session.add(occurrence)
                await self.session.flush()
            return occurrence, True
        except IntegrityError:
            winner = await self.occurrence(occurrence.id, for_update=True)
            if winner is None:
                raise
            return winner, False

    async def add_action(self, action: CareReminderAction) -> None:
        self.session.add(action)
        await self.session.flush()
