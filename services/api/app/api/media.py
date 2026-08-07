from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.media_access import MediaAccessService
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.persistence.repositories.media_repository import MediaRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Media"])


class SignedUrlResponse(BaseModel):
    url: str
    expires_at: datetime


@router.post("/v1/media/{mediaId}/download-url", response_model=SignedUrlResponse)
async def create_signed_download_url(
    mediaId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> SignedUrlResponse:
    if context.organization_id is None or context.role not in {
        "PLATFORM_ADMIN",
        "SHELTER_ADMIN",
        "STAFF",
    }:
        raise DomainError("media_access_denied", "無法查看此照片", 403)
    media = await MediaRepository(session, context.organization_id).require_formal(mediaId)
    expires_seconds = 300
    url = await MediaAccessService(MinioStorageAdapter(), context.organization_id).signed_url(
        media_organization_id=media.organization_id,
        object_key=media.object_key,
        expires_seconds=expires_seconds,
    )
    return SignedUrlResponse(
        url=url,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_seconds),
    )
