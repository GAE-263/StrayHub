from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.growth_diary import GrowthDiaryDraft, GrowthDiaryEntry
from services.api.app.persistence.models.identity import LineUserBinding, OrganizationMembership

# Organization-scoped operational roles that get pushed a LINE notification
# for a "concern"-flagged entry — not PLATFORM_ADMIN, which is a cross-tenant
# super-admin role with no single shelter to notify about.
_GROWTH_DIARY_ALERT_ROLES = ("STAFF", "SHELTER_ADMIN")


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

    async def list_staff_line_user_ids(self) -> list[str]:
        """Every active STAFF/SHELTER_ADMIN in this organization who also has
        an active LINE binding — the push targets for a "concern"-flagged
        entry (see _run_growth_diary_ai_analysis in line_webhook.py)."""
        result = await self.session.execute(
            select(LineUserBinding.line_user_id)
            .join(
                OrganizationMembership,
                OrganizationMembership.user_id == LineUserBinding.user_id,
            )
            .where(
                OrganizationMembership.organization_id == self.organization_id,
                OrganizationMembership.role.in_(_GROWTH_DIARY_ALERT_ROLES),
                OrganizationMembership.status == "active",
                LineUserBinding.status == "active",
            )
        )
        return list(result.scalars())


async def list_entries_for_inquiries(
    session: AsyncSession, inquiry_ids: list[UUID], *, limit: int = 10
) -> list[GrowthDiaryEntry]:
    """Cross-organization by design, like `list_inquiries_for_adopter` — an
    adopter's 日記回顧 spans every shelter they've ever adopted through."""
    if not inquiry_ids:
        return []
    result = await session.execute(
        select(GrowthDiaryEntry)
        .where(GrowthDiaryEntry.inquiry_id.in_(inquiry_ids))
        .order_by(GrowthDiaryEntry.created_at.desc())
        .limit(limit)
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
