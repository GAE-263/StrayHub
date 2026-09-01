from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError, ErrorResponse
from services.api.app.application.media_access import (
    MediaAccessService,
    verify_adoption_photo_object_key,
    verify_adoption_photo_token,
)
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.media_repository import MediaRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Media"])


class SignedUrlResponse(BaseModel):
    url: str
    expires_at: datetime


@router.get(
    "/v1/public/adoption/animals/{animalId}/photo",
    response_class=Response,
    responses={404: {"model": ErrorResponse, "description": "照片不存在或連結已失效"}},
    openapi_extra={"security": []},
)
async def public_adoption_animal_photo(
    animalId: UUID,  # noqa: N803
    token: str,
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> Response:
    """Serve one short-lived, tenant-checked photo without exposing private MinIO."""
    claims = verify_adoption_photo_token(token, animal_id=animalId)
    await set_organization_scope(session, claims.organization_id)
    animal = await AnimalRepository(session, claims.organization_id).get(animalId)
    if (
        animal is None
        or animal.status != "active"
        or not animal.is_adoptable
        or not animal.current_photo_key
    ):
        raise DomainError("adoption_photo_not_found", "照片不存在或連結已失效", 404)
    verify_adoption_photo_object_key(claims, animal.current_photo_key)
    result = await session.execute(
        select(MediaAsset).where(
            MediaAsset.organization_id == claims.organization_id,
            MediaAsset.object_key == animal.current_photo_key,
        )
    )
    media = result.scalar_one_or_none()
    if (
        media is None
        or media.status != "processed"
        or not media.exif_removed
        or not media.content_type.startswith("image/")
    ):
        raise DomainError("adoption_photo_not_found", "照片不存在或連結已失效", 404)
    try:
        content = await MinioStorageAdapter().get(
            scope=ObjectScope(claims.organization_id), key=animal.current_photo_key
        )
    except Exception as exc:
        raise DomainError("adoption_photo_not_found", "照片不存在或連結已失效", 404) from exc
    return Response(
        content=content,
        media_type=media.content_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
