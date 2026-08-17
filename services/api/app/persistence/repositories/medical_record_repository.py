from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.medical_care import MedicalRecord


class MedicalRecordRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, record_id: UUID, *, for_update: bool = False) -> MedicalRecord | None:
        query = select(MedicalRecord).where(
            MedicalRecord.id == record_id,
            MedicalRecord.organization_id == self.organization_id,
        )
        if for_update:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def list(
        self,
        animal_id: UUID,
        *,
        occurred_from: date | None = None,
        occurred_to: date | None = None,
        record_type: str | None = None,
        search: str | None = None,
        include_archived: bool = False,
    ) -> list[MedicalRecord]:
        conditions = [
            MedicalRecord.organization_id == self.organization_id,
            MedicalRecord.animal_id == animal_id,
        ]
        if not include_archived:
            conditions.append(MedicalRecord.status == "active")
        if occurred_from:
            conditions.append(
                MedicalRecord.occurred_at
                >= datetime.combine(occurred_from, time.min, tzinfo=timezone.utc)
            )
        if occurred_to:
            conditions.append(
                MedicalRecord.occurred_at
                < datetime.combine(occurred_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
            )
        if record_type:
            conditions.append(MedicalRecord.record_type == record_type)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                or_(MedicalRecord.title.ilike(pattern), MedicalRecord.content.ilike(pattern))
            )
        result = await self.session.execute(
            select(MedicalRecord)
            .where(and_(*conditions))
            .order_by(MedicalRecord.occurred_at.desc(), MedicalRecord.id.desc())
        )
        return list(result.scalars())

    async def add(self, record: MedicalRecord) -> MedicalRecord:
        self.session.add(record)
        await self.session.flush()
        return record
