from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import require_admin_context, require_staff_or_admin
from services.api.app.application.audit_service import AuditService
from services.api.app.application.qr_token_service import (
    QrTokenService,
    printable_token_for,
)
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.models.shelter_area import ShelterArea
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management/qr-codes", tags=["Management Settings"])


class QrCreateRequest(BaseModel):
    animal_id: UUID


class ManagementQrCodeListItem(BaseModel):
    id: UUID
    organization_id: UUID
    animal_id: UUID
    animal_name: str
    shelter_number: str | None
    animal_status: str
    area_name: str | None
    status: Literal["active", "revoked"]
    revoked: bool
    created_at: datetime
    deep_link: str | None
    token: None


class ManagementQrCodeListResponse(BaseModel):
    items: list[ManagementQrCodeListItem]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


def _payload(value: AnimalQrCode, token: str | None = None) -> dict:
    printable_token = token or (
        printable_token_for(value) if value.status == "active" and not value.revoked else None
    )
    return {
        "id": str(value.id),
        "organization_id": str(value.organization_id),
        "animal_id": str(value.animal_id),
        "status": value.status,
        "revoked": value.revoked,
        "token": None,
        "deep_link": (
            f"/animal-confirmation?organization_id={value.organization_id}"
            f"&qr_token={printable_token}"
            if printable_token
            else None
        ),
    }


def _list_payload(
    qr_code: AnimalQrCode,
    animal: Animal,
    area: ShelterArea | None,
) -> dict:
    return {
        **_payload(qr_code),
        "animal_name": animal.name,
        "shelter_number": animal.shelter_number,
        "animal_status": animal.status,
        "area_name": area.name if area else None,
        "created_at": qr_code.created_at,
    }


@router.get("", response_model=ManagementQrCodeListResponse)
async def list_qr_codes(
    animal_id: UUID | None = Query(default=None),  # noqa: B008
    query: str | None = Query(default=None, max_length=200),  # noqa: B008
    status_filter: Literal["all", "active", "revoked"] = Query(  # noqa: B008
        default="all", alias="status"
    ),
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=20, ge=1, le=100),  # noqa: B008
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    rows, total = await QrCodeRepository(session, organization_id).list_management(
        animal_id=animal_id,
        query=query,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_list_payload(qr_code, animal, area) for qr_code, animal, area in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_qr_code(
    payload: QrCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_admin_context(context)
    service = QrTokenService(
        AnimalRepository(session, organization_id),
        QrCodeRepository(session, organization_id),
    )
    value, token, created = await service.create_or_reuse(animal_id=payload.animal_id)
    if created:
        await AuditService(session).record(
            organization_id=organization_id,
            actor_user_id=context.user_id,
            action="qr_code.created",
            resource_type="AnimalQrCode",
            resource_id=value.id,
            source_channel="api",
            after={"animal_id": str(payload.animal_id), "token_issued": True},
        )
    await session.commit()
    return _payload(value, token)


@router.post("/{qr_id}/revoke")
async def revoke_qr_code(
    qr_id: UUID,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_admin_context(context)
    value = await session.scalar(
        select(AnimalQrCode).where(
            AnimalQrCode.id == qr_id,
            AnimalQrCode.organization_id == organization_id,
        )
    )
    if value is None:
        raise DomainError("qr_code_not_found", "QR Code 不存在或無法存取", 404)
    value.status = "revoked"
    value.revoked = True
    await AuditService(session).record(
        organization_id=organization_id,
        actor_user_id=context.user_id,
        action="qr_code.revoked",
        resource_type="AnimalQrCode",
        resource_id=value.id,
        source_channel="api",
    )
    await session.commit()
    return _payload(value)


@router.post("/{qr_id}/regenerate")
async def regenerate_qr_code(
    qr_id: UUID,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_admin_context(context)
    service = QrTokenService(
        AnimalRepository(session, organization_id),
        QrCodeRepository(session, organization_id),
    )
    previous = await service.qr_codes.get(qr_id)
    if previous is None:
        raise DomainError("qr_code_not_found", "QR Code 不存在或無法存取", 404)
    value, token = await service.regenerate(qr_code_id=qr_id)
    await AuditService(session).record(
        organization_id=organization_id,
        actor_user_id=context.user_id,
        action="qr_code.regenerated",
        resource_type="AnimalQrCode",
        resource_id=value.id,
        source_channel="api",
        before={"replaced_qr_id": str(previous.id)},
        after={"animal_id": str(value.animal_id), "token_issued": True},
    )
    await session.commit()
    return _payload(value, token)
