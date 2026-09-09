from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.animal_profile import (
    AnimalProfile,
    AnimalProfileUpdate,
    profile_values,
)
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.medical_care import CareReminderSeries
from services.api.app.persistence.models.shelter_area import ShelterArea

ALLOWED_MANAGEMENT_PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


@dataclass(frozen=True)
class ManagementAnimalPhoto:
    object_key: str
    content_type: str
    checksum: str


class ManagementAnimalService:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @staticmethod
    def payload(animal: Animal, area: ShelterArea | None) -> dict:
        return {
            **AnimalProfile(**profile_values(animal)).model_dump(mode="json"),
            "id": str(animal.id),
            "organization_id": str(animal.organization_id),
            "name": animal.name,
            "shelter_number": animal.shelter_number,
            "photo_key": animal.current_photo_key,
            "status": animal.status,
            "area_id": str(area.id) if area else None,
            "area_name": area.name if area else None,
            "area_type": area.area_type if area else None,
            "species": animal.species,
            "breed": animal.breed,
            "size": animal.size,
            "energy": animal.energy,
            "temperament": animal.temperament or [],
            "is_adoptable": animal.is_adoptable,
            "adoption_notes": animal.adoption_notes,
        }

    @staticmethod
    def _valid_photo_media(animal: Animal, media: MediaAsset | None) -> bool:
        return bool(
            animal.current_photo_key
            and media is not None
            and media.status == "processed"
            and media.exif_removed
            and media.content_type in ALLOWED_MANAGEMENT_PHOTO_TYPES
            and media.checksum
        )

    async def _read_payload(
        self,
        animal: Animal,
        area: ShelterArea | None,
        media: MediaAsset | None,
    ) -> dict:
        payload = self.payload(animal, area)
        payload["photo_url"] = None
        payload["area_path"] = area.name if area else None
        if area is not None and getattr(area, "parent_id", None):
            parent_name = await self.session.scalar(
                select(ShelterArea.name).where(
                    ShelterArea.id == area.parent_id,
                    ShelterArea.organization_id == self.organization_id,
                )
            )
            if parent_name:
                payload["area_path"] = f"{parent_name} / {area.name}"
        if media is not None and self._valid_photo_media(animal, media):
            payload["photo_url"] = f"/v1/management/animals/{animal.id}/photo?v={media.checksum}"
        return payload

    async def photo(self, animal_id: UUID) -> ManagementAnimalPhoto:
        row = await self.session.execute(
            select(Animal, MediaAsset)
            .outerjoin(
                MediaAsset,
                and_(
                    MediaAsset.organization_id == self.organization_id,
                    MediaAsset.object_key == Animal.current_photo_key,
                ),
            )
            .where(
                Animal.id == animal_id,
                Animal.organization_id == self.organization_id,
            )
        )
        pair = row.one_or_none()
        if pair is None:
            raise DomainError("animal_photo_not_found", "照片不存在或無法存取", 404)
        animal, media = pair
        if not self._valid_photo_media(animal, media):
            raise DomainError("animal_photo_not_found", "照片不存在或無法存取", 404)
        assert animal.current_photo_key is not None and media is not None
        return ManagementAnimalPhoto(
            object_key=animal.current_photo_key,
            content_type=media.content_type,
            checksum=media.checksum,
        )

    async def list(
        self,
        *,
        query: str | None,
        area_id: UUID | None,
        status: str,
        page: int,
        page_size: int,
    ) -> dict:
        filters = [Animal.organization_id == self.organization_id]
        if status != "all":
            filters.append(Animal.status == status)
        if area_id is not None:
            filters.append(Animal.area_id == area_id)
        if query:
            pattern = f"%{query}%"
            filters.append(or_(Animal.name.ilike(pattern), Animal.shelter_number.ilike(pattern)))
        total = await self.session.scalar(select(func.count(Animal.id)).where(*filters))
        rows = await self.session.execute(
            select(Animal, ShelterArea, MediaAsset)
            .outerjoin(
                ShelterArea,
                and_(
                    ShelterArea.id == Animal.area_id,
                    ShelterArea.organization_id == self.organization_id,
                ),
            )
            .outerjoin(
                MediaAsset,
                and_(
                    MediaAsset.organization_id == self.organization_id,
                    MediaAsset.object_key == Animal.current_photo_key,
                ),
            )
            .where(*filters)
            .order_by(Animal.name, Animal.shelter_number, Animal.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [
                await self._read_payload(animal, area, media) for animal, area, media in rows.all()
            ],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }

    async def get(self, animal_id: UUID) -> dict:
        row = await self.session.execute(
            select(Animal, ShelterArea, MediaAsset)
            .outerjoin(
                ShelterArea,
                and_(
                    ShelterArea.id == Animal.area_id,
                    ShelterArea.organization_id == self.organization_id,
                ),
            )
            .outerjoin(
                MediaAsset,
                and_(
                    MediaAsset.organization_id == self.organization_id,
                    MediaAsset.object_key == Animal.current_photo_key,
                ),
            )
            .where(Animal.id == animal_id, Animal.organization_id == self.organization_id)
        )
        pair = row.one_or_none()
        if pair is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        animal, area, media = pair
        return {"animal": await self._read_payload(animal, area, media)}

    async def update_profile(
        self, animal_id: UUID, *, changes: AnimalProfileUpdate, actor_user_id: UUID
    ) -> dict:
        animal = (
            await self.session.execute(
                select(Animal)
                .where(
                    Animal.id == animal_id,
                    Animal.organization_id == self.organization_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if animal is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        before = AnimalProfile(**profile_values(animal))
        try:
            after = AnimalProfile(**(before.model_dump() | changes.model_dump(exclude_unset=True)))
        except ValidationError as exc:
            raise DomainError(
                "invalid_animal_profile", "出生日期不得晚於入園日期；估計出生日期需填寫日期", 422
            ) from exc
        if before != after:
            for field, value in after.model_dump().items():
                setattr(animal, field, value)
            await AuditService(self.session).record(
                organization_id=self.organization_id,
                actor_user_id=actor_user_id,
                action="animal.profile_updated",
                resource_type="Animal",
                resource_id=animal.id,
                source_channel="api",
                before=before.model_dump(mode="json"),
                after=after.model_dump(mode="json"),
            )
        result = await self.get(animal_id)
        await self.session.commit()
        return result

    async def update_status(
        self, animal_id: UUID, *, status: str, reason: str, actor_user_id: UUID
    ) -> dict:
        """Update an animal status and suspend future medical series atomically."""
        if not reason.strip():
            raise DomainError("animal_status_reason_required", "狀態異動需要原因", 422)
        animal = (
            await self.session.execute(
                select(Animal)
                .where(
                    Animal.id == animal_id,
                    Animal.organization_id == self.organization_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if animal is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        if animal.status == status:
            return {"animal": self.payload(animal, None), "suspended_series_count": 0}
        before_status = animal.status
        animal.status = status
        suspended_count = 0
        if status != "active":
            series_rows = list(
                (
                    await self.session.execute(
                        select(CareReminderSeries)
                        .where(
                            CareReminderSeries.organization_id == self.organization_id,
                            CareReminderSeries.animal_id == animal_id,
                            CareReminderSeries.status == "active",
                        )
                        .with_for_update()
                    )
                ).scalars()
            )
            now = datetime.now(timezone.utc)
            for series in series_rows:
                series.status = "suspended"
                series.suspended_at = now
                series.suspend_reason = reason.strip()
                series.version += 1
                suspended_count += 1
                await AuditService(self.session).record(
                    organization_id=self.organization_id,
                    actor_user_id=actor_user_id,
                    action="care_reminder.suspended",
                    resource_type="CareReminderSeries",
                    resource_id=series.id,
                    source_channel="api",
                    before={"status": "active"},
                    after={"status": "suspended", "reason": reason.strip()},
                )
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=actor_user_id,
            action="animal.status_changed",
            resource_type="Animal",
            resource_id=animal.id,
            source_channel="api",
            before={"status": before_status},
            after={"status": status, "reason": reason.strip()},
        )
        await self.session.commit()
        return {"animal": self.payload(animal, None), "suspended_series_count": suspended_count}

    async def update_adoption_fields(
        self,
        animal_id: UUID,
        *,
        species: str | None,
        breed: str | None,
        size: str | None,
        energy: str | None,
        temperament: builtins.list[str],
        is_adoptable: bool,
        adoption_notes: str | None,
        actor_user_id: UUID,
    ) -> dict:
        animal = (
            await self.session.execute(
                select(Animal)
                .where(
                    Animal.id == animal_id,
                    Animal.organization_id == self.organization_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if animal is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        before = {
            "species": animal.species,
            "breed": animal.breed,
            "size": animal.size,
            "energy": animal.energy,
            "temperament": animal.temperament,
            "is_adoptable": animal.is_adoptable,
            "adoption_notes": animal.adoption_notes,
        }
        animal.species = species
        animal.breed = breed
        animal.size = size
        animal.energy = energy
        animal.temperament = temperament
        animal.is_adoptable = is_adoptable
        animal.adoption_notes = adoption_notes
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=actor_user_id,
            action="animal.adoption_fields_updated",
            resource_type="Animal",
            resource_id=animal.id,
            source_channel="api",
            before=before,
            after={
                "species": species,
                "breed": breed,
                "size": size,
                "energy": energy,
                "temperament": temperament,
                "is_adoptable": is_adoptable,
                "adoption_notes": adoption_notes,
            },
        )
        await self.session.commit()
        return {"animal": self.payload(animal, None)}
