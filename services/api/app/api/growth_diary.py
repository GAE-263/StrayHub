from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError, ErrorResponse
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.growth_diary_service import GrowthDiaryManagementService
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management/growth-diary-entries", tags=["Management Growth Diary"])
ERROR_RESPONSES = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422)}


class GrowthDiaryAiSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal[
        "pending",
        "succeeded",
        "failed",
        "unconfigured",
        "not_applicable",
        "legacy",
        "unavailable",
    ]
    provenance_status: Literal["available", "legacy_missing", "unavailable"]
    mood: Literal["positive", "neutral", "concern"] | None
    adopter_reply: str | None
    staff_summary: str | None


class GrowthDiaryAiProvenance(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provenance_status: Literal["available", "legacy_missing", "unavailable"]
    provider: str | None
    model_name: str | None
    model_version: str | None
    prompt_version: str | None
    output_schema_version: str | None
    analyzed_at: datetime | None


class GrowthDiaryListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class GrowthDiaryDetail(GrowthDiaryListItem):
    ai_provenance: GrowthDiaryAiProvenance
    ai_raw_output: dict[str, Any] | str | None


class GrowthDiaryListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[GrowthDiaryListItem]
    page: int
    page_size: int
    total: int


@router.get("", response_model=GrowthDiaryListResponse, responses=ERROR_RESPONSES)
async def list_growth_diary_entries(
    query: str | None = Query(default=None, max_length=120),  # noqa: B008
    mood: Literal["all", "concern", "positive", "neutral", "unanalyzed"] = Query(default="all"),  # noqa: B008
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=50, ge=1, le=100),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> GrowthDiaryListResponse:
    organization_id = require_staff_or_admin(context)
    result = await GrowthDiaryManagementService(session, organization_id).list(
        page=page,
        page_size=page_size,
        query=query,
        mood=mood,
    )
    return GrowthDiaryListResponse.model_validate(result)


@router.get("/{entryId}", response_model=GrowthDiaryDetail, responses=ERROR_RESPONSES)
async def get_growth_diary_entry(
    entryId: UUID,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> GrowthDiaryDetail:
    organization_id = require_staff_or_admin(context)
    result = await GrowthDiaryManagementService(session, organization_id).detail(entryId)
    return GrowthDiaryDetail.model_validate(result)


@router.get(
    "/{entryId}/photo",
    response_class=Response,
    responses={
        **ERROR_RESPONSES,
        200: {
            "description": "Buffered final WebP, authenticated and scoped to the active shelter",
            "headers": {
                "Cache-Control": {"schema": {"type": "string", "const": "private, no-store"}},
                "X-Content-Type-Options": {"schema": {"type": "string", "const": "nosniff"}},
            },
            "content": {"image/webp": {"schema": {"type": "string", "contentEncoding": "binary"}}},
        },
    },
)
async def get_growth_diary_photo(
    entryId: UUID,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> Response:
    organization_id = require_staff_or_admin(context)
    photo = await GrowthDiaryManagementService(session, organization_id).photo(entryId)
    try:
        content = await MinioStorageAdapter().get(
            scope=ObjectScope(organization_id),
            key=photo.object_key,
        )
    except Exception as exc:
        raise DomainError("growth_diary_entry_not_found", "毛孩日記不存在或無法存取", 404) from exc
    return Response(
        content=content,
        media_type="image/webp",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
