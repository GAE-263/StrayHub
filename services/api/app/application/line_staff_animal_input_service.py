"""工作人員以 LINE / LIFF 作為輸入介面，資料落回 StrayHub CRM。

LINE/LIFF 只是輸入介面；動物基本資料與健康紀錄的「家」在 StrayHub 後端。
本服務刻意把儲存埠（ObjectStoragePort）以參數注入，方便單元測試以 in-memory
假儲存替換，不必依賴 MinIO。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.domain.organization_timezone import validate_timezone
from services.api.app.infrastructure.storage.ports import ObjectStoragePort
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.models.medical_care import (
    MedicalRecord,
    MedicalRecordMedia,
    MedicalRecordType,
)

# LINE 健康回報的 status（前端 config 定義）對映成醫療紀錄標題用的中文標籤。
HEALTH_STATUS_LABELS = {
    "healthy": "健康",
    "needs_medical": "需要就醫",
    "in_treatment": "治療中",
    "neutered": "已絕育",
    "under_observation": "觀察中",
}

ALLOWED_PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_ANIMAL_NAME_LENGTH = 200
MAX_SHELTER_NUMBER_LENGTH = 120


@dataclass(frozen=True)
class UploadedPhoto:
    """已從 multipart 讀出的照片位元組與宣告的 content-type。"""

    data: bytes
    content_type: str


class LineStaffAnimalInputService:
    def __init__(
        self,
        session: AsyncSession,
        organization_id: UUID,
        storage: ObjectStoragePort,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.media = MediaProcessingService(storage)

    async def create_animal(
        self,
        *,
        actor_user_id: UUID,
        animal_data: dict,
        photo: UploadedPhoto,
    ) -> dict:
        self._validate_photo_type(photo)
        name = (animal_data.get("name") or "").strip()
        if not name:
            raise DomainError("animal_name_required", "動物名稱不得為空白", 422)
        if len(name) > MAX_ANIMAL_NAME_LENGTH:
            raise DomainError("animal_name_too_long", "動物名稱過長", 422)
        shelter_number = (animal_data.get("tempAnimalId") or "").strip() or None
        if shelter_number is not None and len(shelter_number) > MAX_SHELTER_NUMBER_LENGTH:
            raise DomainError("shelter_number_too_long", "收容編號過長", 422)
        if shelter_number is not None:
            existing_animal_id = (
                await self.session.execute(
                    select(Animal.id).where(
                        Animal.organization_id == self.organization_id,
                        Animal.shelter_number == shelter_number,
                    )
                )
            ).scalar_one_or_none()
            if existing_animal_id is not None:
                raise DomainError("animal_already_exists", "此收容編號已建立", 409)
        animal = Animal(
            organization_id=self.organization_id,
            name=name,
            shelter_number=shelter_number,
            status="active",
        )
        self.session.add(animal)
        try:
            # Claim the unique shelter number before storing external media. A concurrent retry
            # therefore fails without leaving an unreferenced object behind.
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DomainError("animal_already_exists", "此收容編號已建立", 409) from exc
        asset = await self._store_photo(photo, purpose="line_staff_animal")
        animal.current_photo_key = asset.object_key
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=actor_user_id,
            action="animal.created",
            resource_type="Animal",
            resource_id=animal.id,
            source_channel="line",
            after={
                "name": name,
                "shelter_number": shelter_number,
                "photo_key": asset.object_key,
                "status": "active",
            },
        )
        await self.session.commit()
        return {"success": True, "animalId": str(animal.id)}

    async def add_health_record(
        self,
        *,
        actor_user_id: UUID,
        animal_id: UUID,
        health_record: dict,
        submitted_at: str | None,
        photo: UploadedPhoto | None,
    ) -> dict:
        if photo is not None:
            self._validate_photo_type(photo)
        description = (health_record.get("description") or "").strip()
        if not description:
            raise DomainError("health_record_description_required", "健康狀況說明不得為空白", 422)
        status_code = (health_record.get("status") or "").strip()
        if status_code not in HEALTH_STATUS_LABELS:
            raise DomainError("invalid_health_status", "健康狀態不在允許清單", 422)
        animal = (
            await self.session.execute(
                select(Animal).where(
                    Animal.id == animal_id,
                    Animal.organization_id == self.organization_id,
                )
            )
        ).scalar_one_or_none()
        if animal is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        tz = await self._organization_timezone()
        occurred_at = self._resolve_occurred_at(submitted_at, tz)
        label = HEALTH_STATUS_LABELS[status_code]
        title = f"健康回報：{label}"
        if submitted_at:
            existing_record_id = (
                await self.session.execute(
                    select(MedicalRecord.id).where(
                        MedicalRecord.organization_id == self.organization_id,
                        MedicalRecord.animal_id == animal_id,
                        MedicalRecord.occurred_at == occurred_at,
                        MedicalRecord.title == title,
                        MedicalRecord.content == description,
                        MedicalRecord.created_by_user_id == actor_user_id,
                    )
                )
            ).scalar_one_or_none()
            if existing_record_id is not None:
                return {"success": True, "recordId": str(existing_record_id)}
        record = MedicalRecord(
            organization_id=self.organization_id,
            animal_id=animal_id,
            occurred_at=occurred_at,
            occurred_timezone=tz,
            record_type=MedicalRecordType.OTHER.value,
            title=title,
            content=description,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        self.session.add(record)
        await self.session.flush()
        if photo is not None:
            asset = await self._store_photo(photo, purpose="line_health_record")
            self.session.add(
                MedicalRecordMedia(
                    organization_id=self.organization_id,
                    medical_record_id=record.id,
                    media_asset_id=asset.id,
                    attached_by_user_id=actor_user_id,
                )
            )
            await self.session.flush()
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=actor_user_id,
            action="medical_record.created",
            resource_type="MedicalRecord",
            resource_id=record.id,
            source_channel="line",
            after={
                "animal_id": str(animal_id),
                "record_type": MedicalRecordType.OTHER.value,
                "health_status": status_code,
                "title": record.title,
            },
        )
        await self.session.commit()
        return {"success": True, "recordId": str(record.id)}

    async def _store_photo(self, photo: UploadedPhoto, *, purpose: str) -> MediaAsset:
        self._validate_photo_type(photo)
        object_key = f"line-staff/{self.organization_id}/{uuid4().hex}"
        stored = await self.media.store_cleaned(
            organization_id=self.organization_id,
            object_key=object_key,
            data=photo.data,
            declared_content_type=photo.content_type,
        )
        asset = MediaAsset(
            organization_id=self.organization_id,
            object_key=stored.key,
            content_type=stored.metadata.content_type,
            checksum=stored.metadata.checksum,
            status="processed",
            purpose=purpose,
            exif_removed=True,
        )
        self.session.add(asset)
        await self.session.flush()
        return asset

    @staticmethod
    def _validate_photo_type(photo: UploadedPhoto) -> None:
        if photo.content_type not in ALLOWED_PHOTO_TYPES:
            raise DomainError("unsupported_media_type", "照片格式不支援", 422)

    async def _organization_timezone(self) -> str:
        organization = (
            await self.session.execute(
                select(Organization).where(Organization.id == self.organization_id)
            )
        ).scalar_one_or_none()
        if organization is None:
            raise DomainError("organization_not_found", "收容所不存在", 404)
        return validate_timezone(organization.timezone)

    @staticmethod
    def _resolve_occurred_at(submitted_at: str | None, tz: str) -> datetime:
        parsed: datetime | None = None
        if submitted_at:
            try:
                parsed = datetime.fromisoformat(submitted_at)
            except ValueError:
                parsed = None
        if parsed is None:
            parsed = datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(tz))
        return parsed.astimezone(timezone.utc)
