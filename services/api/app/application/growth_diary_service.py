from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.growth_diary import GrowthDiaryEntry
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
    note: str | None
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
    trusted_photo = bool(entry.photo_key and entry.photo_content_type == "image/webp")
    return GrowthDiaryListItem(
        id=entry.id,
        inquiry_id=entry.inquiry_id,
        animal_id=entry.animal_id,
        animal_name=animal.name,
        shelter_number=animal.shelter_number,
        has_photo=entry.photo_key is not None,
        photo_endpoint=(
            f"/v1/management/growth-diary-entries/{entry.id}/photo" if trusted_photo else None
        ),
        note=entry.note,
        ai_analysis=_summary(entry),
        created_at=entry.created_at,
    )


class GrowthDiaryManagementService:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.repository = GrowthDiaryRepository(session, organization_id)

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        query: str | None = None,
        mood: str = "all",
    ) -> GrowthDiaryListPage:
        normalized_query = query.strip() if query else None
        total = await self.repository.count_for_management(
            query=normalized_query,
            mood=mood,
        )
        rows = await self.repository.list_for_management(
            page=page,
            page_size=page_size,
            query=normalized_query,
            mood=mood,
        )
        return GrowthDiaryListPage(
            items=[_list_item(entry, animal) for entry, animal in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

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


class GrowthDiaryInboxService:
    """Backward-compatible adapter until the typed router lands."""

    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.service = GrowthDiaryManagementService(session, organization_id)

    async def list(self) -> dict:
        return asdict(await self.service.list())
