from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.growth_diary import GrowthDiaryDraft, GrowthDiaryEntry


class GrowthDiaryRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def add_entry(
        self,
        *,
        inquiry_id: UUID,
        animal_id: UUID,
        adopter_user_id: UUID,
        photo_key: str | None,
        note: str | None,
    ) -> GrowthDiaryEntry:
        entry = GrowthDiaryEntry(
            organization_id=self.organization_id,
            inquiry_id=inquiry_id,
            animal_id=animal_id,
            adopter_user_id=adopter_user_id,
            photo_key=photo_key,
            note=note,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_organization(self) -> list[GrowthDiaryEntry]:
        result = await self.session.execute(
            select(GrowthDiaryEntry)
            .where(GrowthDiaryEntry.organization_id == self.organization_id)
            .order_by(GrowthDiaryEntry.created_at.desc())
        )
        return list(result.scalars())


async def get_pending_draft(
    session: AsyncSession, adopter_user_id: UUID
) -> GrowthDiaryDraft | None:
    """Cross-organization lookup, like `list_inquiries_for_adopter` — the
    pending marker's organization isn't known to the caller until it's read."""
    return await session.get(GrowthDiaryDraft, adopter_user_id)


async def set_pending_draft(
    session: AsyncSession,
    *,
    adopter_user_id: UUID,
    organization_id: UUID,
    inquiry_id: UUID,
    animal_id: UUID,
) -> GrowthDiaryDraft:
    existing = await session.get(GrowthDiaryDraft, adopter_user_id)
    if existing is not None:
        existing.organization_id = organization_id
        existing.inquiry_id = inquiry_id
        existing.animal_id = animal_id
        await session.flush()
        return existing
    draft = GrowthDiaryDraft(
        adopter_user_id=adopter_user_id,
        organization_id=organization_id,
        inquiry_id=inquiry_id,
        animal_id=animal_id,
    )
    session.add(draft)
    await session.flush()
    return draft


async def clear_pending_draft(session: AsyncSession, adopter_user_id: UUID) -> None:
    draft = await session.get(GrowthDiaryDraft, adopter_user_id)
    if draft is not None:
        await session.delete(draft)
        await session.flush()
