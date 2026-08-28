from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.application.media_access import MediaAccessService
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.growth_diary import GrowthDiaryEntry


class GrowthDiaryInboxService:
    """Read-only for now — staff use this list as a basis for post-adoption
    follow-up; there's no status workflow on entries yet (minimal first
    version of the feature)."""

    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def list(self) -> dict:
        rows = await self.session.execute(
            select(GrowthDiaryEntry, Animal)
            .outerjoin(
                Animal,
                and_(
                    Animal.id == GrowthDiaryEntry.animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .where(GrowthDiaryEntry.organization_id == self.organization_id)
            .order_by(GrowthDiaryEntry.created_at.desc())
        )
        items = []
        for entry, animal in rows.all():
            items.append(await self._payload(entry, animal))
        return {"items": items}

    async def _payload(self, entry: GrowthDiaryEntry, animal: Animal | None) -> dict:
        photo_url = None
        if entry.photo_key:
            try:
                photo_url = await MediaAccessService(
                    MinioStorageAdapter(), self.organization_id
                ).signed_url(
                    media_organization_id=self.organization_id,
                    object_key=entry.photo_key,
                    expires_seconds=300,
                )
            except Exception:
                photo_url = None
        return {
            "id": str(entry.id),
            "inquiry_id": str(entry.inquiry_id),
            "animal_id": str(entry.animal_id),
            "animal_name": animal.name if animal else None,
            "shelter_number": animal.shelter_number if animal else None,
            "photo_url": photo_url,
            "note": entry.note,
            "created_at": entry.created_at.isoformat(),
        }
