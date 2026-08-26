from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
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
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management/qr-codes", tags=["Management Settings"])


class QrCreateRequest(BaseModel):
    animal_id: UUID


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


@router.get("")
async def list_qr_codes(
    animal_id: UUID | None = None,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    query = select(AnimalQrCode).where(AnimalQrCode.organization_id == organization_id)
    if animal_id is not None:
        query = query.where(AnimalQrCode.animal_id == animal_id)
    result = await session.execute(query.order_by(AnimalQrCode.created_at.desc()))
    return {"items": [_payload(item) for item in result.scalars()]}


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
