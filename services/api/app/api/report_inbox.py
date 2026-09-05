from __future__ import annotations

from datetime import date
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
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.audit_service import AuditService
from services.api.app.application.report_correction import ReportCorrectionService
from services.api.app.application.report_inbox_service import ReportInboxService
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/management/reports", tags=["Management Reports"])


class CorrectionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    observations: dict | None = None
    note: str | None = None
    animal_id: UUID | None = None


class ArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ProcessReportRequest(BaseModel):
    status: Literal["acknowledged", "follow_up", "resolved"]
    note: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=0)


@router.post("/{report_id}/processing")
async def process_report(
    report_id: UUID,
    payload: ProcessReportRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    if context.user_id is None or context.public_exposure_profile:
        raise DomainError("report_processing_denied", "目前帳號無法更新處理紀錄", 403)
    report = await ReportInboxService(session, organization_id).process(
        report_id,
        actor_user_id=context.user_id,
        status=payload.status,
        note=payload.note,
        expected_version=payload.expected_version,
    )
    await session.commit()
    return {"report": report}


@router.get("")
async def list_report_inbox(
    from_date: date | None = Query(default=None),  # noqa: B008
    to_date: date | None = Query(default=None),  # noqa: B008
    animal_id: UUID | None = Query(default=None),  # noqa: B008
    report_status: str | None = Query(default=None, alias="status"),  # noqa: B008
    page: int = Query(default=1, ge=1),  # noqa: B008
    page_size: int = Query(default=20, ge=1, le=100),  # noqa: B008
    review_status: Literal["pending", "acknowledged", "follow_up", "resolved"] | None = None,
    attention_level: Literal["normal", "review", "urgent"] | None = None,
    query: str | None = Query(default=None, max_length=120),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    return await ReportInboxService(session, organization_id).list(
        from_date=from_date,
        to_date=to_date,
        animal_id=animal_id,
        report_status=report_status,
        page=page,
        page_size=page_size,
        review_status=review_status,
        attention_level=attention_level,
        query=query,
    )


@router.get("/{report_id}")
async def get_report_detail(
    report_id: UUID,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    report = await ReportInboxService(session, organization_id).detail(report_id)
    report["can_archive"] = (
        context.role in {"SHELTER_ADMIN", "PLATFORM_ADMIN"} and not context.public_exposure_profile
    )
    return {"report": report}


@router.post("/{report_id}/correction")
async def correct_report(
    report_id: UUID,
    payload: CorrectionRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    report = await ReportCorrectionService(
        CareReportRepository(session, organization_id),
        AnimalRepository(session, organization_id),
        audit=AuditService(session),
    ).correct(
        report_id,
        actor_user_id=context.user_id,
        actor_role=context.role,
        observations=payload.observations,
        note=payload.note,
        animal_id=payload.animal_id,
        reason=payload.reason,
    )
    await session.commit()
    return {"report": ReportInboxService.payload(report)}


@router.post("/{report_id}/archive", status_code=status.HTTP_200_OK)
async def archive_report(
    report_id: UUID,
    payload: ArchiveRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    organization_id = require_staff_or_admin(context)
    if context.role == "STAFF":
        raise DomainError("archive_denied", "工作人員無法封存回報", 403)
    report = await ReportCorrectionService(
        CareReportRepository(session, organization_id),
        AnimalRepository(session, organization_id),
        audit=AuditService(session),
    ).archive(report_id, actor_user_id=context.user_id, reason=payload.reason)
    await session.commit()
    return {"report": ReportInboxService.payload(report)}
