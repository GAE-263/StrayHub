from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.media_access import MediaAccessService
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.growth_diary import GrowthDiaryEntry

VALID_STATUSES = {"new", "reviewed"}
VALID_MOODS = {"positive", "neutral", "concern"}


class GrowthDiaryInboxService:
    """Staff use this list as a basis for post-adoption follow-up. `status`
    is the only workflow so far: "new" until a staff member marks an entry
    "reviewed" (see set_status) — no assignment, no multi-stage pipeline."""

    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def list(
        self,
        *,
        search: str | None = None,
        mood: str | None = None,
        entry_status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        filters = [GrowthDiaryEntry.organization_id == self.organization_id]
        if mood:
            filters.append(GrowthDiaryEntry.ai_mood == mood)
        if entry_status:
            filters.append(GrowthDiaryEntry.status == entry_status)
        if from_date:
            filters.append(
                GrowthDiaryEntry.created_at
                >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
            )
        if to_date:
            filters.append(
                GrowthDiaryEntry.created_at
                <= datetime.combine(to_date, time.max, tzinfo=timezone.utc)
            )
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Animal.name.ilike(pattern),
                    Animal.shelter_number.ilike(pattern),
                    GrowthDiaryEntry.note.ilike(pattern),
                )
            )
        base_query = select(GrowthDiaryEntry, Animal).outerjoin(
            Animal,
            and_(
                Animal.id == GrowthDiaryEntry.animal_id,
                Animal.organization_id == self.organization_id,
            ),
        )
        total = await self.session.scalar(
            select(func.count()).select_from(base_query.where(*filters).subquery())
        )
        rows = await self.session.execute(
            base_query.where(*filters)
            .order_by(GrowthDiaryEntry.created_at.desc(), GrowthDiaryEntry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = []
        for entry, animal in rows.all():
            items.append(await self._payload(entry, animal))
        return {"items": items, "page": page, "page_size": page_size, "total": int(total or 0)}

    async def set_status(self, entry_id: UUID, *, entry_status: str) -> dict:
        if entry_status not in VALID_STATUSES:
            raise DomainError(
                "invalid_growth_diary_status", f"不支援的狀態：{entry_status}", 422
            )
        row = await self.session.execute(
            select(GrowthDiaryEntry, Animal)
            .outerjoin(
                Animal,
                and_(
                    Animal.id == GrowthDiaryEntry.animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .where(
                GrowthDiaryEntry.id == entry_id,
                GrowthDiaryEntry.organization_id == self.organization_id,
            )
        )
        pair = row.one_or_none()
        if pair is None:
            raise DomainError("growth_diary_entry_not_found", "找不到這篇成長日記", 404)
        entry, animal = pair
        entry.status = entry_status
        await self.session.flush()
        return await self._payload(entry, animal)

    async def _payload(self, entry: GrowthDiaryEntry, animal: Animal | None) -> dict:
        media = MediaAccessService(MinioStorageAdapter(), self.organization_id)
        photo_urls: list[str] = []
        for photo_key in entry.photo_keys:
            try:
                photo_urls.append(
                    await media.signed_url(
                        media_organization_id=self.organization_id,
                        object_key=photo_key,
                        expires_seconds=300,
                    )
                )
            except Exception:
                continue
        return {
            "id": str(entry.id),
            "inquiry_id": str(entry.inquiry_id),
            "animal_id": str(entry.animal_id),
            "animal_name": animal.name if animal else None,
            "shelter_number": animal.shelter_number if animal else None,
            "photo_urls": photo_urls,
            "note": entry.note,
            "ai_mood": entry.ai_mood,
            "ai_reply": entry.ai_reply,
            "ai_staff_summary": entry.ai_staff_summary,
            "status": entry.status,
            "created_at": entry.created_at.isoformat(),
        }
