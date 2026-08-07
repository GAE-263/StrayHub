from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from services.api.app.persistence.repositories.reportable_scope_repository import (
    ReportableScopeRepository,
)
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


class AnimalListResponse(BaseModel):
    items: list[AnimalCandidateResponse]
    page: int
    page_size: int


class QrResolveRequest(BaseModel):
    qr_token: str


def _candidate(animal, *, organization_id: UUID) -> AnimalCandidateResponse:
    return AnimalCandidateResponse(
        id=animal.id,
        name=animal.name,
        shelter_number=animal.shelter_number,
        photo_url=None,
        organization_id=organization_id,
        can_report=animal.status == "active",
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
    animals = await AnimalRepository(session, context.organization_id).search("")
    if context.role == "VOLUNTEER":
        allowed = await ReportableScopeRepository(
            session, context.organization_id
        ).active_animal_ids(volunteer_user_id=context.user_id)
        animals = [animal for animal in animals if animal.id in allowed]
    start = (page - 1) * page_size
    return AnimalListResponse(
        items=[
            _candidate(animal, organization_id=context.organization_id)
            for animal in animals[start : start + page_size]
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
    animals = await AnimalRepository(session, context.organization_id).search(query)
    if context.role == "VOLUNTEER":
        allowed = await ReportableScopeRepository(
            session, context.organization_id
        ).active_animal_ids(volunteer_user_id=context.user_id)
        animals = [animal for animal in animals if animal.id in allowed]
    start = (page - 1) * page_size
    return AnimalListResponse(
        items=[
            _candidate(animal, organization_id=context.organization_id)
            for animal in animals[start : start + page_size]
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
    qr = await QrCodeRepository(session, context.organization_id).resolve(payload.qr_token)
    if qr is None:
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    animal = await AnimalRepository(session, context.organization_id).get(qr.animal_id)
    if animal is None or (
        context.role == "VOLUNTEER"
        and not await ReportableScopeRepository(
            session, context.organization_id
        ).is_animal_reportable(
            animal_id=animal.id,
            volunteer_user_id=context.user_id,
        )
    ):
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    return _candidate(animal, organization_id=context.organization_id)


@router.post("/v1/animals/{animalId}/confirm", response_model=AnimalCandidateResponse)
async def confirm_animal(
    animalId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> AnimalCandidateResponse:
    if context.organization_id is None:
        raise DomainError("shelter_context_required", "請先選擇目前收容所", 409)
    animal = await AnimalRepository(session, context.organization_id).get(animalId)
    if animal is None or animal.status != "active":
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    if context.role == "VOLUNTEER" and not await ReportableScopeRepository(
        session, context.organization_id
    ).is_animal_reportable(animal_id=animal.id, volunteer_user_id=context.user_id):
        raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
    return _candidate(animal, organization_id=context.organization_id)
