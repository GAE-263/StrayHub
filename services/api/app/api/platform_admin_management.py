from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    authenticated_request_context,
    request_session,
)
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import require_platform_scope
from services.api.app.application.audit_service import AuditService
from services.api.app.application.platform_admin_management import (
    MutationResult,
    PlatformAdminManagementService,
)
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.scope import set_platform_scope
from services.api.app.persistence.repositories.platform_admin_repository import (
    PlatformAdminRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/platform/administrators", tags=["Platform Administrators"])


class PolicySummaryResponse(BaseModel):
    min_active_admins: int
    max_active_admins: int
    active_count: int
    available_slots: int


class PlatformAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    username: str | None
    display_name: str
    user_status: str
    platform_role: str | None
    effective_status: str
    can_enable: bool
    can_disable: bool
    can_demote: bool


class PlatformAdminListResponse(BaseModel):
    policy: PolicySummaryResponse
    items: list[PlatformAdminResponse]


class PlatformAdminCandidateResponse(BaseModel):
    user_id: UUID
    username: str | None
    display_name: str


class CreatePlatformAdminRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=200)
    temporary_password: str = Field(..., min_length=1)


class PromoteRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ReplaceRequest(BaseModel):
    outgoing_user_id: UUID
    replacement_user_id: UUID
    reason: str = Field(..., min_length=1, max_length=500)


class MutationResponse(BaseModel):
    item: PlatformAdminResponse
    policy: PolicySummaryResponse
    operation_id: UUID


class AuditResponse(BaseModel):
    id: UUID
    operation_id: UUID
    actor_user_id: UUID | None
    resource_id: UUID | None
    action: str
    before: dict | None
    after: dict | None
    reason: str | None
    result: str
    created_at: datetime


def _service(session: AsyncSession) -> PlatformAdminManagementService:
    return PlatformAdminManagementService(PlatformAdminRepository(session), Argon2PasswordHasher())


def _item(user, *, active_count: int, max_count: int, min_count: int) -> PlatformAdminResponse:
    is_active = user.status == "active" and user.platform_role == "PLATFORM_ADMIN"
    return PlatformAdminResponse(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        user_status=user.status,
        platform_role=user.platform_role,
        effective_status="active" if is_active else "disabled",
        can_enable=(
            user.platform_role == "PLATFORM_ADMIN"
            and user.status != "active"
            and active_count < max_count
        ),
        can_disable=is_active and active_count > min_count,
        can_demote=(
            user.platform_role == "PLATFORM_ADMIN" and (not is_active or active_count > min_count)
        ),
    )


def _summary(summary) -> PolicySummaryResponse:
    return PolicySummaryResponse(
        min_active_admins=summary.min_active_admins,
        max_active_admins=summary.max_active_admins,
        active_count=summary.active_count,
        available_slots=summary.available_slots,
    )


def _require_platform(context: RequestContext) -> None:
    require_platform_scope(context)


async def _record_denial(session: AsyncSession, context: RequestContext, reason: str) -> None:
    await session.rollback()
    try:
        await set_platform_scope(session)
    except Exception:
        pass
    await AuditService(session).record(
        organization_id=None,
        actor_user_id=context.user_id,
        action="platform_admin.access_denied",
        resource_type="platform",
        source_channel="api",
        reason=reason,
        result="denied",
    )
    await session.commit()


async def _authorize(context: RequestContext, session: AsyncSession) -> None:
    try:
        _require_platform(context)
    except DomainError as exc:
        await _record_denial(session, context, exc.code)
        raise


async def _finish(
    session: AsyncSession,
    context: RequestContext,
    result: MutationResult,
    service: PlatformAdminManagementService,
) -> MutationResponse:
    summary = await service.summary()
    await AuditService(session).record(
        organization_id=None,
        actor_user_id=context.user_id,
        action=result.action,
        resource_type="platform",
        resource_id=result.user.id,
        operation_id=result.operation_id,
        source_channel="api",
        before=result.before,
        after=result.after,
    )
    await session.commit()
    return MutationResponse(
        item=_item(
            result.user,
            active_count=summary.active_count,
            max_count=summary.max_active_admins,
            min_count=summary.min_active_admins,
        ),
        policy=_summary(summary),
        operation_id=result.operation_id,
    )


async def _run_mutation(
    session: AsyncSession,
    context: RequestContext,
    service: PlatformAdminManagementService,
    operation,
) -> MutationResponse:
    await _authorize(context, session)
    try:
        result = await operation()
        return await _finish(session, context, result, service)
    except DomainError as exc:
        await _record_denial(session, context, exc.code)
        raise


@router.get("", response_model=PlatformAdminListResponse)
async def list_platform_admins(
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> PlatformAdminListResponse:
    await _authorize(context, session)
    admins, summary = await _service(session).list_admins()
    return PlatformAdminListResponse(
        policy=_summary(summary),
        items=[
            _item(
                user,
                active_count=summary.active_count,
                max_count=summary.max_active_admins,
                min_count=summary.min_active_admins,
            )
            for user in admins
        ],
    )


@router.post("", response_model=MutationResponse, status_code=status.HTTP_201_CREATED)
async def create_platform_admin(
    payload: CreatePlatformAdminRequest,
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MutationResponse:
    service = _service(session)
    return await _run_mutation(
        session,
        context,
        service,
        lambda: service.create(
            username=payload.username,
            display_name=payload.display_name,
            temporary_password=payload.temporary_password,
        ),
    )


@router.get("/candidates", response_model=list[PlatformAdminCandidateResponse])
async def list_platform_admin_candidates(
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> list[PlatformAdminCandidateResponse]:
    await _authorize(context, session)
    return [
        PlatformAdminCandidateResponse(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
        )
        for user in await PlatformAdminRepository(session).list_candidates()
    ]


@router.post("/replacements", response_model=MutationResponse)
async def replace_platform_admin(
    payload: ReplaceRequest,
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MutationResponse:
    service = _service(session)
    return await _run_mutation(
        session,
        context,
        service,
        lambda: service.replace(
            outgoing_user_id=payload.outgoing_user_id,
            replacement_user_id=payload.replacement_user_id,
        ),
    )


@router.get("/audit", response_model=list[AuditResponse])
async def list_platform_audit(
    user_id: UUID | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> list[AuditResponse]:
    await _authorize(context, session)
    return [
        AuditResponse(
            id=value.id,
            operation_id=value.operation_id,
            actor_user_id=value.actor_user_id,
            resource_id=value.resource_id,
            action=value.action,
            before=value.before_data,
            after=value.after_data,
            reason=value.reason,
            result=value.result,
            created_at=value.created_at,
        )
        for value in await PlatformAdminRepository(session).audit_records(
            user_id=user_id, action=action, limit=limit
        )
    ]


@router.post("/{userId}/promote", response_model=MutationResponse)
async def promote_platform_admin(
    userId: UUID,  # noqa: N803
    payload: PromoteRequest | None = None,
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MutationResponse:
    service = _service(session)
    return await _run_mutation(session, context, service, lambda: service.promote(userId))


@router.post("/{userId}/enable", response_model=MutationResponse)
async def enable_platform_admin(
    userId: UUID,  # noqa: N803
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MutationResponse:
    service = _service(session)
    return await _run_mutation(session, context, service, lambda: service.enable(userId))


@router.post("/{userId}/disable", response_model=MutationResponse)
async def disable_platform_admin(
    userId: UUID,  # noqa: N803
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MutationResponse:
    service = _service(session)
    return await _run_mutation(session, context, service, lambda: service.disable(userId))


@router.post("/{userId}/demote", response_model=MutationResponse)
async def demote_platform_admin(
    userId: UUID,  # noqa: N803
    context: RequestContext = Depends(authenticated_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> MutationResponse:
    service = _service(session)
    return await _run_mutation(session, context, service, lambda: service.demote(userId))
