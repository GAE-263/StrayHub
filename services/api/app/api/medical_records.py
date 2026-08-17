# ruff: noqa: B008
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.medical_care_common import medical_permission
from services.api.app.application.medical_record_media_service import (
    ALLOWED_MEDICAL_MEDIA_TYPES,
)
from services.api.app.application.medical_record_service import MedicalRecordService
from services.api.app.domain.medical_care_access import require_medical_view, require_record_write
from services.api.app.domain.organization_timezone import validate_timezone
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.models.medical_care import (
    MedicalRecord,
    MedicalRecordMedia,
    MedicalRecordType,
)
from services.api.app.persistence.repositories.medical_record_repository import (
    MedicalRecordRepository,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Medical Records"])


class MedicalRecordCreateRequest(BaseModel):
    occurred_at: datetime
    record_type: MedicalRecordType
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    clinic: str | None = Field(default=None, max_length=300)
    veterinarian: str | None = Field(default=None, max_length=200)
    weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    media_ids: list[UUID] = Field(default_factory=list, max_length=8)

    @field_validator("title", "content")
    @classmethod
    def trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不得為空白")
        return value


class MedicalRecordUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    occurred_at: datetime | None = None
    record_type: MedicalRecordType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    clinic: str | None = Field(default=None, max_length=300)
    veterinarian: str | None = Field(default=None, max_length=200)
    weight_kg: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    reason: str = Field(min_length=1, max_length=2000)


class MedicalRecordArchiveRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class MedicalRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    animal_id: UUID
    occurred_at: datetime
    occurred_timezone: str
    record_type: str
    title: str
    content: str
    clinic: str | None
    veterinarian: str | None
    weight_kg: Decimal | None
    status: str
    version: int
    created_by_user_id: UUID
    created_at: datetime
    updated_by_user_id: UUID
    updated_at: datetime
    archived_at: datetime | None
    archive_reason: str | None
    media_ids: list[UUID] = []


class MedicalRecordPage(BaseModel):
    items: list[MedicalRecordResponse]
    next_cursor: str | None = None


async def _response(session: AsyncSession, record: MedicalRecord) -> MedicalRecordResponse:
    media_ids = list(
        (
            await session.execute(
                select(MedicalRecordMedia.media_asset_id).where(
                    MedicalRecordMedia.organization_id == record.organization_id,
                    MedicalRecordMedia.medical_record_id == record.id,
                )
            )
        ).scalars()
    )
    payload = MedicalRecordResponse.model_validate(record, from_attributes=True)
    return payload.model_copy(update={"media_ids": media_ids})


async def _scope(
    session: AsyncSession, context: RequestContext, *, write: bool = False
) -> tuple[UUID, Organization]:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    permission = await medical_permission(session, context)
    (require_record_write if write else require_medical_view)(permission)
    organization = (
        await session.execute(
            select(Organization).where(Organization.id == context.organization_id)
        )
    ).scalar_one_or_none()
    if organization is None:
        raise DomainError("organization_not_found", "收容所不存在", 404)
    return context.organization_id, organization


@router.get("/v1/management/animals/{animalId}/medical-records", response_model=MedicalRecordPage)
async def list_medical_records(
    animalId: UUID,  # noqa: N803
    occurred_from: date | None = Query(None),
    occurred_to: date | None = Query(None),
    record_type: MedicalRecordType | None = Query(None),
    search: str | None = Query(None, max_length=200),
    include_archived: bool = Query(False),
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> MedicalRecordPage:
    organization_id, _ = await _scope(session, context)
    animal = (
        await session.execute(
            select(Animal).where(Animal.id == animalId, Animal.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if animal is None:
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    items = await MedicalRecordRepository(session, organization_id).list(
        animalId,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        record_type=record_type.value if record_type else None,
        search=search,
        include_archived=include_archived,
    )
    return MedicalRecordPage(items=[await _response(session, item) for item in items])


@router.post(
    "/v1/management/animals/{animalId}/medical-records",
    response_model=MedicalRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_medical_record(
    animalId: UUID,
    payload: MedicalRecordCreateRequest,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> MedicalRecordResponse:
    organization_id, organization = await _scope(session, context, write=True)
    MedicalRecordService.validate(
        title=payload.title, content=payload.content, weight_kg=payload.weight_kg
    )
    animal = (
        await session.execute(
            select(Animal).where(Animal.id == animalId, Animal.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if animal is None:
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    occurred_at = (
        payload.occurred_at
        if payload.occurred_at.tzinfo
        else payload.occurred_at.replace(tzinfo=ZoneInfo(validate_timezone(organization.timezone)))
    )
    record = MedicalRecord(
        organization_id=organization_id,
        animal_id=animalId,
        occurred_at=occurred_at.astimezone(timezone.utc),
        occurred_timezone=validate_timezone(organization.timezone),
        record_type=payload.record_type.value,
        title=payload.title,
        content=payload.content,
        clinic=payload.clinic,
        veterinarian=payload.veterinarian,
        weight_kg=payload.weight_kg,
        created_by_user_id=context.user_id,
        updated_by_user_id=context.user_id,
    )
    await MedicalRecordRepository(session, organization_id).add(record)
    if payload.media_ids:
        media_rows = list(
            (
                await session.execute(
                    select(MediaAsset).where(
                        MediaAsset.id.in_(payload.media_ids),
                        MediaAsset.organization_id == organization_id,
                        MediaAsset.status == "processed",
                        MediaAsset.exif_removed.is_(True),
                        MediaAsset.content_type.in_(ALLOWED_MEDICAL_MEDIA_TYPES),
                    )
                )
            ).scalars()
        )
        if len(media_rows) != len(set(payload.media_ids)):
            raise DomainError("medical_media_invalid", "附件不存在、未完成清理或格式不受支援", 422)
        for media_id in payload.media_ids:
            session.add(
                MedicalRecordMedia(
                    organization_id=organization_id,
                    medical_record_id=record.id,
                    media_asset_id=media_id,
                    attached_by_user_id=context.user_id,
                )
            )
    await AuditService(session).record(
        organization_id=organization_id,
        actor_user_id=context.user_id,
        action="medical_record.created",
        resource_type="MedicalRecord",
        resource_id=record.id,
        source_channel="api",
        after=record,
    )
    await session.commit()
    return await _response(session, record)


@router.get("/v1/management/medical-records/{recordId}", response_model=MedicalRecordResponse)
async def get_medical_record(
    recordId: UUID,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> MedicalRecordResponse:  # noqa: N803
    organization_id, _ = await _scope(session, context)
    record = await MedicalRecordRepository(session, organization_id).get(recordId)
    if record is None:
        raise DomainError("medical_record_not_found", "醫療紀錄不存在或無法存取", 404)
    return await _response(session, record)


@router.patch("/v1/management/medical-records/{recordId}", response_model=MedicalRecordResponse)
async def update_medical_record(
    recordId: UUID,
    payload: MedicalRecordUpdateRequest,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> MedicalRecordResponse:  # noqa: N803
    organization_id, organization = await _scope(session, context, write=True)
    record = await MedicalRecordRepository(session, organization_id).get(recordId, for_update=True)
    if record is None:
        raise DomainError("medical_record_not_found", "醫療紀錄不存在或無法存取", 404)
    if record.status != "active" or record.version != payload.expected_version:
        raise DomainError(
            "medical_record_version_conflict", "醫療紀錄已更新或已封存，請重新載入", 409
        )
    MedicalRecordService.validate(
        title=payload.title or record.title,
        content=payload.content or record.content,
        weight_kg=payload.weight_kg if payload.weight_kg is not None else record.weight_kg,
    )
    before = {
        field: getattr(record, field)
        for field in (
            "occurred_at",
            "record_type",
            "title",
            "content",
            "clinic",
            "veterinarian",
            "weight_kg",
            "version",
        )
    }
    for field in (
        "occurred_at",
        "record_type",
        "title",
        "content",
        "clinic",
        "veterinarian",
        "weight_kg",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(record, field, value.value if isinstance(value, MedicalRecordType) else value)
    if record.occurred_at.tzinfo is None:
        record.occurred_at = record.occurred_at.replace(tzinfo=timezone.utc)
    record.occurred_at = record.occurred_at.astimezone(timezone.utc)
    record.version += 1
    record.updated_by_user_id = context.user_id
    after = {field: getattr(record, field) for field in before}
    await AuditService(session).record_correction(
        organization_id=organization_id,
        actor_user_id=context.user_id,
        resource_type="MedicalRecord",
        resource_id=record.id,
        before=before,
        after=after,
        reason=payload.reason,
    )
    await session.commit()
    return await _response(session, record)


@router.post(
    "/v1/management/medical-records/{recordId}/archive", response_model=MedicalRecordResponse
)
async def archive_medical_record(
    recordId: UUID,
    payload: MedicalRecordArchiveRequest,
    context: RequestContext = Depends(current_request_context),
    session: AsyncSession = Depends(request_session),
) -> MedicalRecordResponse:  # noqa: N803
    organization_id, _ = await _scope(session, context, write=True)
    record = await MedicalRecordRepository(session, organization_id).get(recordId, for_update=True)
    if record is None:
        raise DomainError("medical_record_not_found", "醫療紀錄不存在或無法存取", 404)
    if record.status != "active" or record.version != payload.expected_version:
        raise DomainError(
            "medical_record_version_conflict", "醫療紀錄已更新或已封存，請重新載入", 409
        )
    record.status = "archived"
    record.version += 1
    record.archived_by_user_id = context.user_id
    record.archived_at = datetime.now(timezone.utc)
    record.archive_reason = payload.reason
    record.updated_by_user_id = context.user_id
    await AuditService(session).record_archive(
        organization_id=organization_id,
        actor_user_id=context.user_id,
        resource_type="MedicalRecord",
        resource_id=record.id,
        reason=payload.reason,
    )
    await session.commit()
    return await _response(session, record)
