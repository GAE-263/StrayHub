from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    authenticated_request_context,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import (
    AnimalCandidate,
    AnimalSelectionService,
    issue_animal_confirmation_token,
)
from services.api.app.application.media_access import MediaAccessService
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.domain.animal_profile import AnimalSex
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.persistence.database.scope import (
    set_authentication_user_organization_scope,
    set_organization_scope,
)
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Animal Selection"])


class AnimalCandidateResponse(BaseModel):
    id: UUID
    name: str
    shelter_number: str | None
    photo_url: str | None = None
    cage: str | None = None
    area: str | None = None
    organization_id: UUID
    can_report: bool
    sex: AnimalSex = "unknown"
    breed: str | None = None
    birth_date: date | None = None
    birth_date_estimated: bool = False
    age_description: str | None = None
    care_guidance: str | None = None


class AnimalConfirmationResponse(AnimalCandidateResponse):
    confirmation_token: str


class AnimalListResponse(BaseModel):
    items: list[AnimalCandidateResponse]
    page: int
    page_size: int


class QrResolveRequest(BaseModel):
    qr_token: str


class QrCandidateOrganizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qr_token: str = Field(min_length=1)
    candidate_organization_id: UUID


class QrCandidateOrganizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    organization_name: str = Field(min_length=1)


async def _candidate(
    candidate: AnimalCandidate, *, organization_id: UUID
) -> AnimalCandidateResponse:
    animal = candidate.animal
    area = candidate.area
    photo_url = None
    if animal.current_photo_key:
        try:
            photo_url = await MediaAccessService(MinioStorageAdapter(), organization_id).signed_url(
                media_organization_id=organization_id,
                object_key=animal.current_photo_key,
                expires_seconds=300,
            )
        except Exception:
            # Photo access must not prevent identity confirmation.
            photo_url = None
    return AnimalCandidateResponse(
        id=animal.id,
        name=animal.name,
        shelter_number=animal.shelter_number,
        photo_url=photo_url,
        cage=area.name if area is not None and area.area_type == "cage" else None,
        area=area.name if area is not None and area.area_type != "cage" else None,
        organization_id=organization_id,
        can_report=animal.status == "active",
        sex=getattr(animal, "sex", None) or "unknown",
        breed=getattr(animal, "breed", None),
        birth_date=getattr(animal, "birth_date", None),
        birth_date_estimated=getattr(animal, "birth_date_estimated", None) or False,
        age_description=getattr(animal, "age_description", None),
        care_guidance=getattr(animal, "care_guidance", None),
    )


def _selection_service(session: AsyncSession, organization_id: UUID) -> AnimalSelectionService:
    animals = AnimalRepository(session, organization_id)
    return AnimalSelectionService(
        animals,
        QrCodeRepository(session, organization_id),
        VolunteerReportingAuthorizationService(AuthenticationRepository(session), animals),
    )


@router.get("/v1/animals", response_model=AnimalListResponse)
async def list_reportable_animals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AnimalListResponse:
    if context.organization_id is None and not context.platform_scope:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    if context.organization_id is None:
        return AnimalListResponse(items=[], page=page, page_size=page_size)
    candidates = await _selection_service(session, context.organization_id).list_candidates(
        user_id=context.user_id,
        organization_id=context.organization_id,
        membership_id=context.membership_id,
        role=context.role,
    )
    start = (page - 1) * page_size
    return AnimalListResponse(
        items=[
            await _candidate(candidate, organization_id=context.organization_id)
            for candidate in candidates[start : start + page_size]
        ],
        page=page,
        page_size=page_size,
    )


@router.get("/v1/animals/search", response_model=AnimalListResponse)
async def search_animals(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AnimalListResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    candidates = await _selection_service(session, context.organization_id).list_candidates(
        user_id=context.user_id,
        organization_id=context.organization_id,
        membership_id=context.membership_id,
        role=context.role,
        query=query,
    )
    start = (page - 1) * page_size
    return AnimalListResponse(
        items=[
            await _candidate(candidate, organization_id=context.organization_id)
            for candidate in candidates[start : start + page_size]
        ],
        page=page,
        page_size=page_size,
    )


@router.post("/v1/qr-tokens/resolve", response_model=AnimalCandidateResponse)
async def resolve_qr_token(
    payload: QrResolveRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AnimalCandidateResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    candidate = await _selection_service(session, context.organization_id).resolve_qr(
        raw_token=payload.qr_token,
        user_id=context.user_id,
        organization_id=context.organization_id,
        membership_id=context.membership_id,
        role=context.role,
    )
    return await _candidate(candidate, organization_id=context.organization_id)


@router.post(
    "/v1/qr-tokens/candidate-organization",
    response_model=QrCandidateOrganizationResponse,
)
async def authorize_qr_candidate_organization(
    payload: QrCandidateOrganizationRequest,
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> QrCandidateOrganizationResponse:
    original_organization_id = context.organization_id
    target_organization_id = payload.candidate_organization_id
    await set_authentication_user_organization_scope(
        session, context.user_id, target_organization_id
    )
    try:
        authentication = AuthenticationRepository(session)
        organization = await authentication.get_organization(target_organization_id)
        animals = AnimalRepository(session, target_organization_id)
        await VolunteerReportingAuthorizationService(authentication, animals).authorize(
            user_id=context.user_id,
            organization_id=target_organization_id,
        )
        await set_organization_scope(session, target_organization_id)
        qr_code = await QrCodeRepository(session, target_organization_id).resolve(payload.qr_token)
        animal = None if qr_code is None else await animals.get(qr_code.animal_id)
        if (
            qr_code is None
            or animal is None
            or qr_code.organization_id != target_organization_id
            or animal.organization_id != target_organization_id
            or qr_code.animal_id != animal.id
            or animal.status != "active"
        ):
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        assert organization is not None
        return QrCandidateOrganizationResponse(
            organization_id=organization.id,
            organization_name=organization.name,
        )
    finally:
        if original_organization_id is not None:
            await set_organization_scope(session, original_organization_id)


@router.post("/v1/animals/{animalId}/confirm", response_model=AnimalConfirmationResponse)
async def confirm_animal(
    animalId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AnimalConfirmationResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    if context.membership_id is None or context.session_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    candidate = await _selection_service(session, context.organization_id).confirm(
        animal_id=animalId,
        user_id=context.user_id,
        organization_id=context.organization_id,
        membership_id=context.membership_id,
        role=context.role,
    )
    response = await _candidate(candidate, organization_id=context.organization_id)
    return AnimalConfirmationResponse(
        **response.model_dump(),
        confirmation_token=issue_animal_confirmation_token(
            user_id=context.user_id,
            organization_id=context.organization_id,
            membership_id=context.membership_id,
            session_id=context.session_id,
            animal_id=animalId,
        ),
    )
