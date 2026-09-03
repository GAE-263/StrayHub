from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
from services.api.app.persistence.models.animal import Animal
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
        photo_content_type: str | None = None,
        note: str | None,
    ) -> GrowthDiaryEntry:
        if not note and photo_key is None:
            raise DomainError("growth_diary_content_required", "日記必須包含文字或照片", 422)
        if photo_key is not None and photo_content_type != "image/webp":
            raise DomainError("untrusted_growth_diary_photo", "日記照片格式無法確認", 422)
        if photo_key is None and photo_content_type is not None:
            raise DomainError("invalid_growth_diary_photo_metadata", "日記照片資料不一致", 422)

        inquiry_result = await self.session.execute(
            select(AdoptionInquiry).where(
                AdoptionInquiry.id == inquiry_id,
                AdoptionInquiry.organization_id == self.organization_id,
                AdoptionInquiry.target_animal_id == animal_id,
                AdoptionInquiry.adopter_user_id == adopter_user_id,
            )
        )
        if inquiry_result.scalar_one_or_none() is None:
            raise DomainError("growth_diary_source_not_found", "日記來源不存在或無法存取", 404)

        animal_result = await self.session.execute(
            select(Animal).where(
                Animal.id == animal_id,
                Animal.organization_id == self.organization_id,
            )
        )
        if animal_result.scalar_one_or_none() is None:
            raise DomainError("growth_diary_source_not_found", "日記來源不存在或無法存取", 404)

        entry = GrowthDiaryEntry(
            organization_id=self.organization_id,
            inquiry_id=inquiry_id,
            animal_id=animal_id,
            adopter_user_id=adopter_user_id,
            photo_key=photo_key,
            photo_content_type=photo_content_type,
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

    def _management_query(self, *, query: str | None = None, mood: str | None = None):
        statement = (
            select(GrowthDiaryEntry, Animal)
            .join(
                Animal,
                and_(
                    Animal.id == GrowthDiaryEntry.animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .join(
                AdoptionInquiry,
                and_(
                    AdoptionInquiry.id == GrowthDiaryEntry.inquiry_id,
                    AdoptionInquiry.organization_id == self.organization_id,
                    AdoptionInquiry.target_animal_id == GrowthDiaryEntry.animal_id,
                ),
            )
            .where(GrowthDiaryEntry.organization_id == self.organization_id)
        )
        normalized_query = query.strip().lower() if query else ""
        if normalized_query:
            pattern = f"%{normalized_query}%"
            statement = statement.where(
                or_(
                    func.lower(Animal.name).like(pattern),
                    func.lower(Animal.shelter_number).like(pattern),
                )
            )
        if mood == "unanalyzed":
            statement = statement.where(GrowthDiaryEntry.ai_mood.is_(None))
        elif mood and mood != "all":
            statement = statement.where(GrowthDiaryEntry.ai_mood == mood)
        return statement

    async def count_for_management(
        self, *, query: str | None = None, mood: str | None = None
    ) -> int:
        statement = self._management_query(query=query, mood=mood).with_only_columns(
            func.count(GrowthDiaryEntry.id), maintain_column_froms=True
        )
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_for_management(
        self,
        *,
        page: int,
        page_size: int,
        query: str | None = None,
        mood: str | None = None,
    ) -> list[tuple[GrowthDiaryEntry, Animal]]:
        statement = (
            self._management_query(query=query, mood=mood)
            .order_by(GrowthDiaryEntry.created_at.desc(), GrowthDiaryEntry.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        result = await self.session.execute(statement)
        return list(result.all())

    async def get_for_management(self, entry_id: UUID) -> tuple[GrowthDiaryEntry, Animal] | None:
        result = await self.session.execute(
            self._management_query().where(GrowthDiaryEntry.id == entry_id)
        )
        return result.one_or_none()

    async def get_photo_for_management(self, entry_id: UUID) -> GrowthDiaryEntry | None:
        statement = (
            self._management_query()
            .with_only_columns(GrowthDiaryEntry, maintain_column_froms=True)
            .where(GrowthDiaryEntry.id == entry_id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

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
