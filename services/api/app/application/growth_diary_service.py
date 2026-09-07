from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.growth_diary import GrowthDiaryEntry
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.repositories.growth_diary_repository import GrowthDiaryRepository


@dataclass(frozen=True)
class GrowthDiaryAiSummary:
    status: str
    provenance_status: str
    mood: str | None
    adopter_reply: str | None
    staff_summary: str | None


@dataclass(frozen=True)
class GrowthDiaryAiProvenance:
    provenance_status: str
    provider: str | None
    model_name: str | None
    model_version: str | None
    prompt_version: str | None
    output_schema_version: str | None
    analyzed_at: datetime | None


@dataclass(frozen=True)
class GrowthDiaryListItem:
    id: UUID
    inquiry_id: UUID
    animal_id: UUID
    animal_name: str | None
    shelter_number: str | None
    has_photo: bool
    photo_endpoint: str | None
    photo_endpoints: tuple[str, ...]
    note: str | None
    status: str
    status_updated_at: datetime | None
    entry_date: date
    ai_analysis: GrowthDiaryAiSummary
    created_at: datetime


@dataclass(frozen=True)
class GrowthDiaryDetail(GrowthDiaryListItem):
    ai_provenance: GrowthDiaryAiProvenance
    ai_raw_output: dict[str, Any] | str | None


@dataclass(frozen=True)
class GrowthDiaryListPage:
    items: list[GrowthDiaryListItem]
    page: int
    page_size: int
    total: int
    timezone: str


@dataclass(frozen=True)
class GrowthDiaryPhoto:
    object_key: str
    content_type: str


def _provenance_status(entry: GrowthDiaryEntry) -> str:
    if all(
        (
            entry.ai_provider,
            entry.ai_model_name,
            entry.ai_model_version,
            entry.ai_prompt_version,
            entry.ai_output_schema_version,
            entry.ai_analyzed_at,
        )
    ):
        return "available"
    if entry.ai_analysis_status is None:
        return "legacy_missing"
    return "unavailable"


def _summary(entry: GrowthDiaryEntry) -> GrowthDiaryAiSummary:
    return GrowthDiaryAiSummary(
        status=entry.ai_analysis_status or "legacy",
        provenance_status=_provenance_status(entry),
        mood=entry.ai_mood,
        adopter_reply=entry.ai_reply,
        staff_summary=entry.ai_staff_summary,
    )


def _list_item(entry: GrowthDiaryEntry, animal: Animal) -> GrowthDiaryListItem:
    photo_keys = list(entry.photo_keys or ([] if entry.photo_key is None else [entry.photo_key]))
    trusted_photo = bool(photo_keys and entry.photo_content_type == "image/webp")
    photo_endpoints = tuple(
        f"/v1/management/growth-diary-entries/{entry.id}/photos/{index}"
        for index in range(len(photo_keys))
    ) if trusted_photo else ()
    return GrowthDiaryListItem(
        id=entry.id,
        inquiry_id=entry.inquiry_id,
        animal_id=entry.animal_id,
        animal_name=animal.name,
        shelter_number=animal.shelter_number,
        has_photo=bool(photo_keys),
        photo_endpoint=(
            f"/v1/management/growth-diary-entries/{entry.id}/photo" if trusted_photo else None
        ),
        photo_endpoints=photo_endpoints,
        note=entry.note,
        status=entry.status,
        status_updated_at=entry.status_updated_at,
        entry_date=entry.entry_date,
        ai_analysis=_summary(entry),
        created_at=entry.created_at,
    )


class GrowthDiaryManagementService:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id
        self.repository = GrowthDiaryRepository(session, organization_id)

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        query: str | None = None,
        mood: str = "all",
        status: str = "all",
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> GrowthDiaryListPage:
        normalized_query = query.strip() if query else None
        total = await self.repository.count_for_management(
            query=normalized_query,
            mood=mood,
            status=status,
            from_date=from_date,
            to_date=to_date,
        )
        rows = await self.repository.list_for_management(
            page=page,
            page_size=page_size,
            query=normalized_query,
            mood=mood,
            status=status,
            from_date=from_date,
            to_date=to_date,
        )
        organization_timezone = await self.session.scalar(
            select(Organization.timezone).where(Organization.id == self.organization_id)
        )
        return GrowthDiaryListPage(
            items=[_list_item(entry, animal) for entry, animal in rows],
            page=page,
            page_size=page_size,
            total=total,
            timezone=organization_timezone or "UTC",
        )

    async def set_status(
        self, entry_id: UUID, *, status: str, actor_user_id: UUID
    ) -> GrowthDiaryDetail:
        if status not in {"new", "reviewed"}:
            raise DomainError("invalid_growth_diary_status", f"不支援的狀態：{status}", 422)
        status_change = await self.repository.set_status(
            entry_id, status=status, actor_user_id=actor_user_id
        )
        if status_change is None:
            raise DomainError("growth_diary_entry_not_found", "毛孩日記不存在或無法存取", 404)
        entry, previous_status = status_change
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=actor_user_id,
            action="status_update",
            resource_type="growth_diary_entry",
            resource_id=entry_id,
            source_channel="api",
            before={"status": previous_status},
            after={"status": status},
        )
        return await self.detail(entry_id)

    async def detail(self, entry_id: UUID) -> GrowthDiaryDetail:
        row = await self.repository.get_for_management(entry_id)
        if row is None:
            raise DomainError("growth_diary_entry_not_found", "毛孩日記不存在或無法存取", 404)
        entry, animal = row
        item = _list_item(entry, animal)
        return GrowthDiaryDetail(
            **asdict(item),
            ai_provenance=GrowthDiaryAiProvenance(
                provenance_status=_provenance_status(entry),
                provider=entry.ai_provider,
                model_name=entry.ai_model_name,
                model_version=entry.ai_model_version,
                prompt_version=entry.ai_prompt_version,
                output_schema_version=entry.ai_output_schema_version,
                analyzed_at=entry.ai_analyzed_at,
            ),
            ai_raw_output=entry.ai_raw_output,
        )

    async def photo(self, entry_id: UUID) -> GrowthDiaryPhoto:
        entry = await self.repository.get_photo_for_management(entry_id)
        if entry is None or not entry.photo_key or entry.photo_content_type != "image/webp":
            raise DomainError("growth_diary_entry_not_found", "毛孩日記不存在或無法存取", 404)
        return GrowthDiaryPhoto(entry.photo_key, entry.photo_content_type)

    async def photo_at(self, entry_id: UUID, index: int) -> GrowthDiaryPhoto:
        entry = await self.repository.get_photo_for_management(entry_id)
        if entry is None or entry.photo_content_type != "image/webp":
            raise DomainError("growth_diary_entry_not_found", "毛孩日記不存在或無法存取", 404)
        keys = list(entry.photo_keys or ([] if entry.photo_key is None else [entry.photo_key]))
        if index < 0 or index >= len(keys):
            raise DomainError("growth_diary_photo_not_found", "毛孩日記照片不存在", 404)
        return GrowthDiaryPhoto(keys[index], entry.photo_content_type)


class GrowthDiaryInboxService:
    """Backward-compatible adapter until the typed router lands."""

    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.service = GrowthDiaryManagementService(session, organization_id)

    async def list(self, **filters) -> dict:
        if "search" in filters:
            filters["query"] = filters.pop("search")
        if "entry_status" in filters:
            filters["status"] = filters.pop("entry_status")
        return jsonable_encoder(asdict(await self.service.list(**filters)))

    async def set_status(
        self, entry_id: UUID, *, entry_status: str, actor_user_id: UUID
    ) -> dict:
        return jsonable_encoder(
            await self.service.set_status(
                entry_id, status=entry_status, actor_user_id=actor_user_id
            )
        )
