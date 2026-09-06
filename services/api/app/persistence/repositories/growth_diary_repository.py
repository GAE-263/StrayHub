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
        """Opens a brand new day's entry — `photo_key` names this first
        message's photo, if any (kept singular in this signature since every
        call site only ever has one photo in hand at a time; see
        append_to_entry for adding to an already-open entry)."""
        entry = GrowthDiaryEntry(
            organization_id=self.organization_id,
            inquiry_id=inquiry_id,
            animal_id=animal_id,
            adopter_user_id=adopter_user_id,
            photo_keys=[photo_key] if photo_key else [],
            note=note,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def append_to_entry(
        self, entry_id: UUID, *, photo_key: str | None, note: str | None
    ) -> GrowthDiaryEntry:
        """Merges one more same-day message onto an already-open entry —
        `note` is appended (paragraph-separated) rather than replacing what's
        there, and `photo_key` (if any) is added to photo_keys rather than
        replacing the existing list, so nothing from earlier the same day is
        lost. See _handle_growth_diary_message for the same-day/new-day
        decision that calls this vs add_entry."""
        entry = await self.session.get(GrowthDiaryEntry, entry_id)
        if entry is None:
            raise ValueError(f"growth diary entry {entry_id} not found")
        if note:
            entry.note = f"{entry.note}\n\n{note}" if entry.note else note
        if photo_key:
            entry.photo_keys = [*entry.photo_keys, photo_key]
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
        if existing.inquiry_id != inquiry_id:
            # Switching to a different animal — today's open thread (if any)
            # belongs to the *previous* animal, so it must not be reused for
            # this one. Leave it as None; the next message opens a fresh
            # entry for the newly-picked animal (see _handle_growth_diary_
            # message). Re-picking the *same* animal deliberately falls
            # through without resetting these, so a repeat "新增一篇" tap for
            # a pet already being talked to today still appends instead of
            # forking a second entry for the same day.
            existing.current_entry_id = None
            existing.entry_date = None
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
