from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.create_report_draft import CreateReportDraftService
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.application.observation_option_usage_service import (
    ObservationOptionUsageService,
)
from services.api.app.application.report_correction import ReportCorrectionService
from services.api.app.application.report_job_dispatch import ReportJobDispatchService
from services.api.app.application.report_submission import ReportSubmissionService
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from services.api.app.persistence.repositories.reportable_scope_repository import (
    ReportableScopeRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Drafts", "Care Reports"])


class DraftCreateRequest(BaseModel):
    animal_id: UUID
    confirmation_token: str


class DraftUpdateRequest(BaseModel):
    answers: dict[str, str] | None = None
    note: str | None = None
    story: str | None = None


class CareReportCreateRequest(BaseModel):
    draft_id: UUID
    observations: dict[str, str]
    note: str | None = None
    story: str | None = None
    media_ids: list[UUID] = []


class CareReportCorrectionRequest(BaseModel):
    reason: str
    observations: dict[str, str] | None = None
    note: str | None = None
    animal_id: UUID | None = None


class ArchiveRequest(BaseModel):
    reason: str


class DraftResponse(BaseModel):
    id: UUID
    opaque_token: str | None = None
    organization_id: UUID
    animal_id: UUID
    volunteer_user_id: UUID
    membership_id: UUID
    current_step: str
    answers: dict
    status: str
    expires_at: datetime


class CareReportResponse(BaseModel):
    id: UUID
    organization_id: UUID
    animal_id: UUID
    status: str
    observations: dict
    observation_snapshots: dict | None = None
    note: str | None = None
    story: str | None = None
    created_at: datetime


def _draft_response(draft, *, opaque_token: str | None = None) -> DraftResponse:
    return DraftResponse(
        id=draft.id,
        opaque_token=opaque_token,
        organization_id=draft.organization_id,
        animal_id=draft.animal_id,
        volunteer_user_id=draft.volunteer_user_id,
        membership_id=draft.membership_id,
        current_step=draft.current_step,
        answers=draft.answers,
        status=draft.status,
        expires_at=draft.expires_at,
    )


def _report_response(report: CareReport) -> CareReportResponse:
    return CareReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        animal_id=report.animal_id,
        status=report.status,
        observations=report.answers,
        observation_snapshots=report.answer_snapshots,
        note=report.note,
        story=report.story,
        created_at=report.created_at,
    )


async def _effective_answer_validator(session: AsyncSession, organization_id: UUID):
    options = await ObservationRepository(session, organization_id).effective_options(
        include_disabled_history=False
    )
    service = EffectiveObservationService(
        {
            option.code: EffectiveOption(
                code=option.code,
                display_name=option.display_name,
                description=option.description,
                requires_note=option.requires_note,
                active=option.status == "active",
            )
            for option in options
        }
    )
    return service.validate_answer


async def _effective_note_validator(session: AsyncSession, organization_id: UUID):
    options = await ObservationRepository(session, organization_id).effective_options(
        include_disabled_history=False
    )
    service = EffectiveObservationService(
        {
            option.code: EffectiveOption(
                code=option.code,
                display_name=option.display_name,
                description=option.description,
                requires_note=option.requires_note,
                active=option.status == "active",
            )
            for option in options
        }
    )
    return service.validate_note_requirement


async def _validate_report_scope(
    session: AsyncSession,
    organization_id: UUID,
    role: str,
    volunteer_user_id: UUID,
    animal_id: UUID,
) -> bool:
    if role != "VOLUNTEER":
        return True
    return await ReportableScopeRepository(session, organization_id).is_animal_reportable(
        animal_id=animal_id,
        volunteer_user_id=volunteer_user_id,
    )


@router.post(
    "/v1/care-report-drafts", response_model=DraftResponse, status_code=status.HTTP_201_CREATED
)
async def create_draft(
    payload: DraftCreateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> DraftResponse:
    if context.organization_id is None or context.membership_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    if context.session_id is None:
        raise DomainError("invalid_session", "Session 無效", 401)
    animal = await AnimalRepository(session, context.organization_id).get(payload.animal_id)
    if animal is None or animal.status != "active":
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    if context.role == "VOLUNTEER" and not await ReportableScopeRepository(
        session, context.organization_id
    ).is_animal_reportable(
        animal_id=animal.id,
        volunteer_user_id=context.user_id,
    ):
        raise DomainError("animal_not_reportable", "動物目前不在你的今日可回報範圍", 403)
    draft, raw_token = await CreateReportDraftService(
        CareReportDraftRepository(session, context.organization_id)
    ).create(
        volunteer_user_id=context.user_id,
        organization_id=context.organization_id,
        membership_id=context.membership_id,
        session_id=context.session_id,
        animal_id=animal.id,
        confirmation_token=payload.confirmation_token,
    )
    await session.commit()
    return _draft_response(draft, opaque_token=raw_token)


@router.get("/v1/care-report-drafts/{draftId}", response_model=DraftResponse)
async def get_draft(
    draftId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> DraftResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    draft = await CareReportDraftRepository(session, context.organization_id).get(draftId)
    if draft is None or draft.volunteer_user_id != context.user_id:
        raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
    return _draft_response(draft)


@router.patch("/v1/care-report-drafts/{draftId}", response_model=DraftResponse)
async def update_draft(
    draftId: UUID,  # noqa: N803
    payload: DraftUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> DraftResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    draft = await CareReportDraftRepository(session, context.organization_id).get(draftId)
    if draft is None or draft.volunteer_user_id != context.user_id or draft.status != "active":
        raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
    if payload.answers:
        draft.answers = {**draft.answers, **payload.answers}
    if payload.note is not None:
        draft.note = payload.note
    if payload.story is not None:
        draft.story = payload.story
    return _draft_response(draft)


@router.delete("/v1/care-report-drafts/{draftId}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    draftId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> Response:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    draft = await CareReportDraftRepository(session, context.organization_id).get(draftId)
    if draft is None or draft.volunteer_user_id != context.user_id or draft.status != "active":
        raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
    draft.status = "cancelled"
    draft.current_step = "cancelled"
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/v1/care-reports", response_model=CareReportResponse, status_code=status.HTTP_201_CREATED
)
async def create_care_report(
    payload: CareReportCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> CareReportResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    organization_id = context.organization_id
    draft_repository = CareReportDraftRepository(session, organization_id)
    draft = await draft_repository.get(payload.draft_id)
    if draft is None or draft.volunteer_user_id != context.user_id:
        raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
    if set(payload.observations) != set(REQUIRED_ANSWER_KEYS):
        raise DomainError("incomplete_answers", "缺少必要回報答案", 422)
    draft.answers = payload.observations
    draft.current_step = "reviewing"
    observation_repository = ObservationRepository(session, context.organization_id)
    options = await observation_repository.effective_options(include_disabled_history=False)
    categories = await observation_repository.categories(include_disabled=True)
    category_codes = {category.id: category.code for category in categories}
    options_by_code = {option.code: option for option in options}
    observation_service = EffectiveObservationService(
        {
            option.code: EffectiveOption(
                code=option.code,
                display_name=option.display_name,
                description=option.description,
                requires_note=option.requires_note,
                active=option.status == "active",
            )
            for option in options
        }
    )
    validator = observation_service.validate_answer
    answer_snapshots = {
        field: {
            "category_code": category_codes[options_by_code[code].category_id],
            "code": code,
            "display_name": observation_service.options[code].display_name,
            "description": observation_service.options[code].description,
            "source": (
                "platform_default"
                if options_by_code[code].organization_id is None
                else "organization_extension"
            ),
        }
        for field, code in payload.observations.items()
        if code in observation_service.options
    }
    animal = await AnimalRepository(session, context.organization_id).get(draft.animal_id)
    if animal is None:
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    report = await ReportSubmissionService(
        draft_repository,
        CareReportRepository(session, context.organization_id),
        answer_validator=validator,
        scope_validator=lambda animal_id: _validate_report_scope(
            session,
            organization_id,
            context.role,
            context.user_id,
            animal_id,
        ),
        audit=AuditService(session),
        note_validator=await _effective_note_validator(session, context.organization_id),
        answer_snapshots=answer_snapshots,
        usage_service=ObservationOptionUsageService(session, context.organization_id),
    ).submit(
        draft_id=draft.id,
        volunteer_user_id=context.user_id,
        animal=animal,
        idempotency_key=idempotency_key,
        note=payload.note,
        story=payload.story,
        media_asset_ids=payload.media_ids,
    )
    await session.commit()
    await ReportJobDispatchService(session_factory).dispatch(
        organization_id=report.organization_id,
        report_id=report.id,
    )
    return _report_response(report)


@router.get("/v1/care-reports/{reportId}", response_model=CareReportResponse)
async def get_care_report(
    reportId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> CareReportResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    report = await CareReportRepository(session, context.organization_id).get(reportId)
    if report is None or (
        context.role == "VOLUNTEER" and report.volunteer_user_id != context.user_id
    ):
        raise DomainError("report_not_found", "照護回報不存在或無法存取", 404)
    return _report_response(report)


@router.patch("/v1/care-reports/{reportId}", response_model=CareReportResponse)
async def correct_care_report(
    reportId: UUID,  # noqa: N803
    payload: CareReportCorrectionRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> CareReportResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    report = await ReportCorrectionService(
        CareReportRepository(session, context.organization_id),
        AnimalRepository(session, context.organization_id),
        answer_validator=await _effective_answer_validator(session, context.organization_id),
        audit=AuditService(session),
        usage_service=ObservationOptionUsageService(session, context.organization_id),
    ).correct(
        reportId,
        actor_user_id=context.user_id,
        actor_role=context.role,
        observations=payload.observations,
        note=payload.note,
        animal_id=payload.animal_id,
        reason=payload.reason,
    )
    await session.commit()
    return _report_response(report)


@router.post("/v1/care-reports/{reportId}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_care_report(
    reportId: UUID,  # noqa: N803
    payload: ArchiveRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> Response:
    if context.organization_id is None or context.role not in {
        "PLATFORM_ADMIN",
        "SHELTER_ADMIN",
        "STAFF",
    }:
        raise DomainError("report_archive_denied", "無法封存此照護回報", 403)
    await ReportCorrectionService(
        CareReportRepository(session, context.organization_id),
        AnimalRepository(session, context.organization_id),
        audit=AuditService(session),
    ).archive(reportId, actor_user_id=context.user_id, reason=payload.reason)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
