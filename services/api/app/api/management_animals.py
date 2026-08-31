from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError, ErrorResponse
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.line_staff_animal_input_service import (
    LineStaffAnimalInputService,
    UploadedPhoto,
)
from services.api.app.application.management_animal_service import ManagementAnimalService
from services.api.app.domain.animal_profile import AnimalProfile, AnimalProfileUpdate
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management/animals", tags=["Management Animals"])

MAX_PHOTO_BYTES = 10 * 1024 * 1024


def _parse_payload(payload: str) -> dict:
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise DomainError("invalid_payload", "payload 不是有效的 JSON", 422) from exc
    if not isinstance(parsed, dict):
        raise DomainError("invalid_payload", "payload 格式錯誤", 422)
    return parsed


async def _read_photo(upload: UploadFile | None) -> UploadedPhoto | None:
    if upload is None:
        return None
    data = await upload.read()
    if not data:
        return None
    if len(data) > MAX_PHOTO_BYTES:
        raise DomainError("media_too_large", "照片超過允許大小", 422)
    return UploadedPhoto(
        data=data,
        content_type=(upload.content_type or "application/octet-stream"),
    )


class AnimalStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=1, max_length=2000)


class ManagementAnimal(AnimalProfile):
    id: UUID
    organization_id: UUID
    name: str
    shelter_number: str | None
    photo_key: str | None
    photo_url: str | None = None
    status: str
    area_id: UUID | None
    area_name: str | None
    area_type: str | None
    area_path: str | None = None
    species: str | None = None
    size: str | None = None
    energy: str | None = None
    temperament: list[str] = Field(default_factory=list)
    is_adoptable: bool = False
    adoption_notes: str | None = None


class ManagementAnimalResponse(BaseModel):
    animal: ManagementAnimal


class ManagementAnimalListResponse(BaseModel):
    items: list[ManagementAnimal]
    page: int
    page_size: int
    total: int


class AnimalAdoptionProfileUpdateRequest(BaseModel):
    species: str | None = Field(default=None, max_length=60)
    breed: str | None = Field(default=None, max_length=120)
    size: str | None = Field(default=None, max_length=30)
    energy: str | None = Field(default=None, max_length=30)
    temperament: list[str] = Field(default_factory=list)
    is_adoptable: bool = False
    adoption_notes: str | None = Field(default=None, max_length=2000)


@router.post("")
async def create_management_animal(
    payload: str = Form(...),  # noqa: B008
    photo: UploadFile = File(...),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    """工作人員以 LINE/LIFF 新增收容動物（multipart：payload JSON + photo）。"""
    organization_id = require_staff_or_admin(context)
    data = _parse_payload(payload)
    animal_data = data.get("animal")
    if not isinstance(animal_data, dict):
        raise DomainError("invalid_payload", "缺少 animal 欄位", 422)
    photo_obj = await _read_photo(photo)
    if photo_obj is None:
        raise DomainError("photo_required", "請附上一張照片", 422)
    service = LineStaffAnimalInputService(session, organization_id, MinioStorageAdapter())
    return await service.create_animal(
        actor_user_id=context.user_id,
        animal_data=animal_data,
        photo=photo_obj,
    )


@router.get("", response_model=ManagementAnimalListResponse)
async def list_management_animals(
    query: str | None = Query(default=None),  # noqa: B008
    area_id: UUID | None = Query(default=None),  # noqa: B008
    status: str = Query(default="active"),  # noqa: B008
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=20, ge=1, le=100),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await ManagementAnimalService(session, organization_id).list(
        query=query,
        area_id=area_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/{animal_id}", response_model=ManagementAnimalResponse)
async def get_management_animal(
    animal_id: UUID,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await ManagementAnimalService(session, organization_id).get(animal_id)


@router.patch(
    "/{animal_id}/profile",
    response_model=ManagementAnimalResponse,
    operation_id="updateManagementAnimalProfile",
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422)},
)
async def update_management_animal_profile(
    animal_id: UUID,
    payload: AnimalProfileUpdate,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await ManagementAnimalService(session, organization_id).update_profile(
        animal_id,
        changes=payload,
        actor_user_id=context.user_id,
    )


@router.patch("/{animal_id}")
async def update_management_animal_status(
    animal_id: UUID,
    payload: AnimalStatusUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await ManagementAnimalService(session, organization_id).update_status(
        animal_id,
        status=payload.status,
        reason=payload.reason,
        actor_user_id=context.user_id,
    )


@router.post("/{animal_id}/health-records")
async def create_management_animal_health_record(
    animal_id: UUID,
    payload: str = Form(...),  # noqa: B008
    photo: UploadFile | None = File(default=None),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    """工作人員以 LINE/LIFF 更新健康紀錄（multipart：payload JSON + 選填 photo）。"""
    organization_id = require_staff_or_admin(context)
    data = _parse_payload(payload)
    health_record = data.get("healthRecord")
    if not isinstance(health_record, dict):
        raise DomainError("invalid_payload", "缺少 healthRecord 欄位", 422)
    photo_obj = await _read_photo(photo)
    service = LineStaffAnimalInputService(session, organization_id, MinioStorageAdapter())
    return await service.add_health_record(
        actor_user_id=context.user_id,
        animal_id=animal_id,
        health_record=health_record,
        submitted_at=data.get("submittedAt"),
        photo=photo_obj,
    )


@router.patch("/{animal_id}/adoption-profile")
async def update_management_animal_adoption_profile(
    animal_id: UUID,
    payload: AnimalAdoptionProfileUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await ManagementAnimalService(session, organization_id).update_adoption_fields(
        animal_id,
        species=payload.species,
        breed=payload.breed,
        size=payload.size,
        energy=payload.energy,
        temperament=payload.temperament,
        is_adoptable=payload.is_adoptable,
        adoption_notes=payload.adoption_notes,
        actor_user_id=context.user_id,
    )
