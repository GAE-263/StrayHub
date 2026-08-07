from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.timeline_service import TimelineService
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.timeline_repository import TimelineRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Timeline"])


def _serialize_day(day, *, media_by_report: dict | None = None) -> dict:
    return {
        "date": day.date.isoformat(),
        "has_report": day.has_report,
        "report_count": day.report_count,
        "no_report_label": None if day.has_report else "當日無回報",
        "reports": [
            {
                "id": str(report.id),
                "submitted_at": report.submitted_at.isoformat(),
                "volunteer_user_id": str(report.volunteer_user_id),
                "animal_name_snapshot": report.animal_name_snapshot,
                "shelter_number_snapshot": report.shelter_number_snapshot,
                "note": report.note,
                "observations": report.answers,
                "status": report.status,
                "ai_job_status": report.ai_job_status,
                "media_ids": [
                    str(media.id) for media in (media_by_report or {}).get(report.id, [])
                ],
            }
            for report in day.reports
        ],
    }


@router.get("/v1/animals/{animalId}/timeline")
async def animal_timeline(
    animalId: UUID,  # noqa: N803
    start_date: date | None = Query(None),  # noqa: B008
    end_date: date | None = Query(None),  # noqa: B008
    _context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> dict:
    # The organization scope comes from the verified request context, never
    # from a query parameter or path segment.
    context = _context
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    if context.role not in {"PLATFORM_ADMIN", "SHELTER_ADMIN", "STAFF"}:
        raise DomainError("timeline_access_denied", "目前帳號無法查看完整歷程", 403)
    animal = await AnimalRepository(session, context.organization_id).get(animalId)
    if animal is None:
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    service = TimelineService(TimelineRepository(session, context.organization_id))
    days = (
        await service.date_range(animal_id=animalId, start_date=start_date, end_date=end_date)
        if start_date is not None and end_date is not None
        else await service.recent(animal_id=animalId, end_date=end_date)
    )
    media_by_report = await TimelineRepository(session, context.organization_id).media_for_reports(
        [report.id for day in days for report in day.reports]
    )
    return {"days": [_serialize_day(day, media_by_report=media_by_report) for day in days]}
