from __future__ import annotations

from datetime import date, datetime, timezone
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
    MAX_PHOTOS_PER_ENTRY = 8
    MAX_NOTE_LENGTH = 2000

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
        entry_date: date | None = None,
    ) -> GrowthDiaryEntry:
        if not note and photo_key is None:
            raise DomainError("growth_diary_content_required", "日記必須包含文字或照片", 422)
        if photo_key is not None and photo_content_type != "image/webp":
            raise DomainError("untrusted_growth_diary_photo", "日記照片格式無法確認", 422)
        if photo_key is None and photo_content_type is not None:
            raise DomainError("invalid_growth_diary_photo_metadata", "日記照片資料不一致", 422)
        if note and len(note) > self.MAX_NOTE_LENGTH:
            raise DomainError("growth_diary_note_too_long", "單日文字紀錄已達上限", 422)

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
            photo_keys=[photo_key] if photo_key else [],
            note=note,
            entry_date=entry_date or datetime.now(timezone.utc).date(),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def append_to_entry(
        self,
        entry_id: UUID,
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
        result = await self.session.execute(
            select(GrowthDiaryEntry)
            .where(
                GrowthDiaryEntry.id == entry_id,
                GrowthDiaryEntry.organization_id == self.organization_id,
                GrowthDiaryEntry.inquiry_id == inquiry_id,
                GrowthDiaryEntry.animal_id == animal_id,
                GrowthDiaryEntry.adopter_user_id == adopter_user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            raise DomainError("growth_diary_source_not_found", "日記來源不存在或無法存取", 404)
        next_note = f"{entry.note}\n\n{note}" if entry.note and note else note or entry.note
        if next_note and len(next_note) > self.MAX_NOTE_LENGTH:
            raise DomainError("growth_diary_note_too_long", "單日文字紀錄已達上限", 422)
        keys = list(entry.photo_keys or ([] if entry.photo_key is None else [entry.photo_key]))
        if photo_key:
            if len(keys) >= self.MAX_PHOTOS_PER_ENTRY:
                raise DomainError("growth_diary_photo_limit", "單日最多可上傳 8 張照片", 422)
            keys.append(photo_key)
            entry.photo_key = photo_key
            entry.photo_content_type = photo_content_type
        entry.note = next_note
        entry.photo_keys = keys
        entry.content_version += 1
        entry.ai_analysis_status = "pending"
        entry.ai_content_version = None
        entry.ai_mood = None
        entry.ai_reply = None
        entry.ai_staff_summary = None
        entry.ai_provider = None
        entry.ai_model_name = None
        entry.ai_model_version = None
        entry.ai_prompt_version = None
        entry.ai_output_schema_version = None
        entry.ai_raw_output = None
        entry.ai_analyzed_at = None
        await self.session.flush()
        return entry

    async def list_for_organization(self) -> list[GrowthDiaryEntry]:
        result = await self.session.execute(
            select(GrowthDiaryEntry)
            .where(GrowthDiaryEntry.organization_id == self.organization_id)
            .order_by(GrowthDiaryEntry.created_at.desc())
        )
        return list(result.scalars())

    def _management_query(
        self,
        *,
        query: str | None = None,
        mood: str | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ):
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
                    func.lower(GrowthDiaryEntry.note).like(pattern),
                )
            )
        if mood == "unanalyzed":
            statement = statement.where(GrowthDiaryEntry.ai_mood.is_(None))
        elif mood and mood != "all":
            statement = statement.where(GrowthDiaryEntry.ai_mood == mood)
        if status and status != "all":
            statement = statement.where(GrowthDiaryEntry.status == status)
        if from_date:
            statement = statement.where(GrowthDiaryEntry.entry_date >= from_date)
        if to_date:
            statement = statement.where(GrowthDiaryEntry.entry_date <= to_date)
        return statement

    async def count_for_management(
        self,
        *,
        query: str | None = None,
        mood: str | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> int:
        statement = self._management_query(
            query=query, mood=mood, status=status, from_date=from_date, to_date=to_date
        ).with_only_columns(func.count(GrowthDiaryEntry.id), maintain_column_froms=True)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_for_management(
        self,
        *,
        page: int,
        page_size: int,
        query: str | None = None,
        mood: str | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[GrowthDiaryEntry, Animal]]:
        statement = (
            self._management_query(
                query=query, mood=mood, status=status, from_date=from_date, to_date=to_date
            )
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

    async def set_status(
        self, entry_id: UUID, *, status: str, actor_user_id: UUID
    ) -> tuple[GrowthDiaryEntry, str] | None:
        result = await self.session.execute(
            select(GrowthDiaryEntry)
            .where(
                GrowthDiaryEntry.id == entry_id,
                GrowthDiaryEntry.organization_id == self.organization_id,
            )
            .with_for_update()
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None
        previous_status = entry.status
        entry.status = status
        entry.status_updated_at = datetime.now(timezone.utc)
        entry.status_updated_by_user_id = actor_user_id
        await self.session.flush()
        return entry, previous_status

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
    result = await session.execute(
        select(GrowthDiaryDraft)
        .where(GrowthDiaryDraft.adopter_user_id == adopter_user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def set_pending_draft(
    session: AsyncSession,
    *,
    adopter_user_id: UUID,
    organization_id: UUID,
    inquiry_id: UUID,
    animal_id: UUID,
) -> GrowthDiaryDraft:
    existing = await get_pending_draft(session, adopter_user_id)
    if existing is not None:
        if existing.inquiry_id != inquiry_id or existing.animal_id != animal_id:
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
