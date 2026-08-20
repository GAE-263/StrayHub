from __future__ import annotations

import base64
import binascii
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    decode_platform_support_reason,
    platform_support_audit_lifecycle,
    request_session,
    validate_platform_support_request,
)
from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.ports.authentication import LineIdentityVerifierPort
from services.api.app.application.volunteer_access_service import (
    VolunteerAccessService,
    VolunteerStatusResult,
)
from services.api.app.application.volunteer_batch_service import VolunteerBatchService
from services.api.app.application.volunteer_notification_service import (
    VolunteerNotificationService,
)
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.line.identity_verification_adapter import (
    configured_line_identity_verifier,
)
from services.api.app.persistence.database.scope import set_platform_support_scope
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Volunteer Applications"])


def require_volunteer_management(
    context: RequestContext,
    organization_id: UUID,
    support_reason: str | None,
) -> str | None:
    if context.platform_scope or context.role == "PLATFORM_ADMIN":
        return validate_platform_support_request(context, organization_id, support_reason)
    if context.organization_id != organization_id or context.role != "SHELTER_ADMIN":
        raise DomainError("volunteer_management_denied", "無法管理此收容所志工資料", 403)
    return None


class VolunteerIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=1)
    shelter_entry_reference: str = Field(min_length=1)


class VolunteerApplicationCreateRequest(VolunteerIdentityRequest):
    client_request_id: UUID
    consent_acknowledged: Literal[True]


class VolunteerApplicationWithdrawRequest(VolunteerIdentityRequest):
    expected_version: int = Field(ge=1)


class PublicOrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    applications_enabled: bool


class VolunteerApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    display_name: str = "LINE 志工"
    status: str
    submitted_at: datetime
    decided_at: datetime | None = None
    decision_reason: str | None = None
    version: int


class VolunteerGrantSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    source_type: str
    policy_version_used: int | None = None
    duration_hours_used: int | None = None
    valid_from: datetime
    expires_at: datetime
    version: int


class VolunteerApplicationStatusResponse(BaseModel):
    organization: PublicOrganizationResponse
    application: VolunteerApplicationResponse | None
    grant: VolunteerGrantSummaryResponse | None
    effective_status: str
    next_actions: list[str]


class VolunteerAccessPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: UUID
    applications_enabled: bool
    default_grant_duration_hours: int
    version: int


class VolunteerAccessPolicyUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    applications_enabled: bool | None = None
    default_grant_duration_hours: int | None = Field(default=None, ge=1)


class VolunteerDecisionItemRequest(BaseModel):
    application_id: UUID
    expected_version: int = Field(ge=1)
    valid_from: datetime | None = None
    expires_at: datetime | None = None


class ExplicitVolunteerDecisionSelection(BaseModel):
    mode: Literal["explicit_items"]
    items: list[VolunteerDecisionItemRequest] = Field(min_length=1, max_length=500)


class VolunteerApplicationBatchFilter(BaseModel):
    status: Literal["pending"] = "pending"
    submitted_from: datetime | None = None
    submitted_to: datetime | None = None


class AllFilteredVolunteerDecisionSelection(BaseModel):
    mode: Literal["all_filtered"]
    filter: VolunteerApplicationBatchFilter
    overrides: list[VolunteerDecisionItemRequest] = Field(default_factory=list, max_length=500)


class VolunteerDecisionBatchRequest(BaseModel):
    operation_id: UUID
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=500)
    default_valid_from: datetime | None = None
    default_expires_at: datetime | None = None
    selection: ExplicitVolunteerDecisionSelection | AllFilteredVolunteerDecisionSelection


class GrantPeriodUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["update_period"]
    expected_version: int = Field(ge=1)
    valid_from: datetime
    expires_at: datetime
    confirm_immediate_expiry: bool = False
    reason: str | None = Field(default=None, max_length=500)


class GrantRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["revoke"]
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class VolunteerNotificationRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    notification_ids: list[UUID] = Field(min_length=1, max_length=500)


@asynccontextmanager
async def volunteer_management_scope(
    *,
    session: AsyncSession,
    context: RequestContext,
    organization_id: UUID,
    support_reason: str | None,
    resource_type: str,
) -> AsyncIterator[str | None]:
    if context.platform_scope or context.role == "PLATFORM_ADMIN":
        try:
            audit_reason = (
                decode_platform_support_reason(support_reason) or "[missing support reason]"
            )
        except DomainError:
            audit_reason = "[invalid support reason]"
        await set_platform_support_scope(session, organization_id)
        async with platform_support_audit_lifecycle(
            AuditService(session),
            context=context,
            target_organization_id=organization_id,
            support_reason=audit_reason,
            resource_type=resource_type,
            session=session,
        ):
            normalized_reason = require_volunteer_management(
                context, organization_id, support_reason
            )
            yield normalized_reason
        return
    require_volunteer_management(context, organization_id, support_reason)
    yield None


def get_line_identity_verifier() -> LineIdentityVerifierPort:
    settings = get_settings()
    return configured_line_identity_verifier(
        app_env=settings.app_env,
        channel_id=settings.line_channel_id,
    )


async def _service_for_entry(
    session: AsyncSession,
    raw_reference: str,
    verifier: LineIdentityVerifierPort,
) -> tuple[VolunteerAccessService, UUID]:
    VolunteerAccessService.validate_entry_reference(raw_reference)
    resolved = await VolunteerAccessRepository.resolve_and_scope(session, raw_reference)
    if resolved is None:
        raise DomainError("entry_unavailable", "此志工入口目前無法使用", 403)
    reference_id, organization_id = resolved
    repository = VolunteerAccessRepository(session, organization_id)
    return (
        VolunteerAccessService(
            repository,
            AuthenticationRepository(session),
            verifier,
            audit=AuditService(session),
            notifications=VolunteerNotificationService(repository),
        ),
        reference_id,
    )


def _response(result: VolunteerStatusResult) -> VolunteerApplicationStatusResponse:
    return VolunteerApplicationStatusResponse.model_validate(
        {
            "organization": result.organization,
            "application": result.application,
            "grant": result.grant,
            "effective_status": result.effective_status,
            "next_actions": result.next_actions,
        }
    )


@router.post(
    "/v1/volunteer-applications/status",
    response_model=VolunteerApplicationStatusResponse,
)
async def resolve_volunteer_application_status(
    payload: VolunteerIdentityRequest,
    session: AsyncSession = Depends(request_session),  # noqa: B008
    verifier: LineIdentityVerifierPort = Depends(get_line_identity_verifier),  # noqa: B008
) -> VolunteerApplicationStatusResponse:
    service, reference_id = await _service_for_entry(
        session, payload.shelter_entry_reference, verifier
    )
    result = await service.status(id_token=payload.id_token, entry_reference_id=reference_id)
    return _response(result)


@router.post(
    "/v1/volunteer-applications",
    response_model=VolunteerApplicationStatusResponse,
)
async def submit_volunteer_application(
    payload: VolunteerApplicationCreateRequest,
    response: Response,
    session: AsyncSession = Depends(request_session),  # noqa: B008
    verifier: LineIdentityVerifierPort = Depends(get_line_identity_verifier),  # noqa: B008
) -> VolunteerApplicationStatusResponse:
    service, reference_id = await _service_for_entry(
        session, payload.shelter_entry_reference, verifier
    )
    result = await service.submit(
        id_token=payload.id_token,
        entry_reference_id=reference_id,
        client_request_id=payload.client_request_id,
        consent_acknowledged=payload.consent_acknowledged,
    )
    await session.commit()
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return _response(result.status)


@router.post(
    "/v1/volunteer-applications/{applicationId}/withdraw",
    response_model=VolunteerApplicationStatusResponse,
)
async def withdraw_volunteer_application(
    applicationId: UUID,  # noqa: N803
    payload: VolunteerApplicationWithdrawRequest,
    session: AsyncSession = Depends(request_session),  # noqa: B008
    verifier: LineIdentityVerifierPort = Depends(get_line_identity_verifier),  # noqa: B008
) -> VolunteerApplicationStatusResponse:
    service, reference_id = await _service_for_entry(
        session, payload.shelter_entry_reference, verifier
    )
    result = await service.withdraw(
        id_token=payload.id_token,
        entry_reference_id=reference_id,
        application_id=applicationId,
        expected_version=payload.expected_version,
    )
    await session.commit()
    return _response(result)


def _management_service(
    session: AsyncSession, repository: VolunteerAccessRepository
) -> VolunteerAccessService:
    return VolunteerAccessService(
        repository,
        AuthenticationRepository(session),
        get_line_identity_verifier(),
        audit=AuditService(session),
        notifications=VolunteerNotificationService(repository),
    )


def _policy_response(policy) -> VolunteerAccessPolicyResponse:
    return VolunteerAccessPolicyResponse.model_validate(policy, from_attributes=True)


def _application_dict(application) -> dict:
    return {
        "id": application.id,
        "organization_id": application.organization_id,
        "display_name": "LINE 志工",
        "status": application.status,
        "submitted_at": application.submitted_at,
        "decided_at": application.decided_at,
        "decision_reason": application.decision_reason,
        "version": application.version,
    }


def _encode_application_cursor(application) -> str:
    raw = f"{application.submitted_at.isoformat()}|{application.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_application_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        submitted_at_raw, application_id_raw = (
            base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
        )
        submitted_at = datetime.fromisoformat(submitted_at_raw)
        if submitted_at.tzinfo is None:
            raise ValueError
        return submitted_at, UUID(application_id_raw)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise DomainError("invalid_cursor", "查詢游標無效", 422) from exc


def _encode_grant_cursor(grant) -> str:
    raw = f"{grant.approved_at.isoformat()}|{grant.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _grant_dict(grant, *, display_name: str = "LINE 志工") -> dict:
    return {
        "id": grant.id,
        "organization_id": grant.organization_id,
        "user_id": grant.user_id,
        "membership_id": grant.membership_id,
        "application_id": grant.application_id,
        "display_name": display_name,
        "status": grant.status,
        "source_type": grant.source_type,
        "policy_version_used": grant.policy_version_used,
        "duration_hours_used": grant.duration_hours_used,
        "valid_from": grant.valid_from,
        "expires_at": grant.expires_at,
        "approved_at": grant.approved_at,
        "revocation_reason": grant.revocation_reason,
        "version": grant.version,
        "notification": None,
    }


def _encode_notification_cursor(delivery) -> str:
    raw = f"{delivery.last_failed_at.isoformat()}|{delivery.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _batch_dict(batch) -> dict:
    return {
        "id": batch.id,
        "organization_id": batch.organization_id,
        "operation_id": batch.operation_id,
        "decision": batch.decision,
        "selection_mode": batch.selection_mode,
        "snapshot_at": batch.snapshot_at,
        "status": batch.status,
        "requested_count": batch.requested_count,
        "processed_count": batch.processed_count,
        "succeeded_count": batch.succeeded_count,
        "conflict_count": batch.conflict_count,
        "failed_count": batch.failed_count,
        "chunk_size": 500,
        "completed_at": batch.completed_at,
        "created_at": batch.created_at,
    }


@router.get(
    "/v1/organizations/{organizationId}/volunteer-access-policy",
    response_model=VolunteerAccessPolicyResponse,
)
async def get_volunteer_access_policy(
    organizationId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> VolunteerAccessPolicyResponse:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="organization_volunteer_access_policy",
    ):
        policy = await VolunteerAccessRepository(session, organizationId).policy()
    await session.commit()
    return _policy_response(policy)


@router.patch(
    "/v1/organizations/{organizationId}/volunteer-access-policy",
    response_model=VolunteerAccessPolicyResponse,
)
async def update_volunteer_access_policy(
    organizationId: UUID,  # noqa: N803
    payload: VolunteerAccessPolicyUpdateRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> VolunteerAccessPolicyResponse:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="organization_volunteer_access_policy",
    ):
        repository = VolunteerAccessRepository(session, organizationId)
        policy = await _management_service(session, repository).update_policy(
            actor_user_id=context.user_id,
            expected_version=payload.expected_version,
            applications_enabled=payload.applications_enabled,
            default_grant_duration_hours=payload.default_grant_duration_hours,
        )
    await session.commit()
    return _policy_response(policy)


@router.get("/v1/organizations/{organizationId}/volunteer-applications")
async def list_volunteer_applications(
    organizationId: UUID,  # noqa: N803
    application_status: str | None = Query(default=None, alias="status"),
    submitted_from: datetime | None = None,
    submitted_to: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> dict:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_application",
    ):
        repository = VolunteerAccessRepository(session, organizationId)
        items = await repository.list_applications(
            status=application_status,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
            cursor=_decode_application_cursor(cursor),
            limit=limit + 1,
        )
        matching_count = await repository.count_applications(
            status=application_status,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
        )
    await session.commit()
    has_more = len(items) > limit
    page_items = items[:limit]
    return {
        "items": [_application_dict(item) for item in page_items],
        "matching_count": matching_count,
        "next_cursor": _encode_application_cursor(page_items[-1]) if has_more else None,
    }


@router.get("/v1/organizations/{organizationId}/volunteer-access-grants")
async def list_volunteer_access_grants(
    organizationId: UUID,  # noqa: N803
    grant_status: str | None = Query(default=None, alias="status"),
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> dict:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_access_grant",
    ):
        repository = VolunteerAccessRepository(session, organizationId)
        grants = await repository.list_grants(
            status=grant_status,
            cursor=_decode_application_cursor(cursor),
            limit=limit + 1,
        )
        identities = AuthenticationRepository(session)
        page_grants = grants[:limit]
        items = []
        for grant in page_grants:
            user = await identities.get_user(grant.user_id)
            items.append(
                _grant_dict(
                    grant,
                    display_name="LINE 志工" if user is None else user.display_name,
                )
            )
    await session.commit()
    return {
        "items": items,
        "next_cursor": _encode_grant_cursor(page_grants[-1]) if len(grants) > limit else None,
    }


@router.patch("/v1/organizations/{organizationId}/volunteer-access-grants/{grantId}")
async def update_volunteer_access_grant(
    organizationId: UUID,  # noqa: N803
    grantId: UUID,  # noqa: N803
    payload: GrantPeriodUpdateRequest | GrantRevokeRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> dict:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_access_grant",
    ):
        repository = VolunteerAccessRepository(session, organizationId)
        arguments = payload.model_dump()
        action = arguments.pop("action")
        grant = await _management_service(session, repository).mutate_grant(
            grant_id=grantId,
            action=action,
            actor_user_id=context.user_id,
            **arguments,
        )
        user = await AuthenticationRepository(session).get_user(grant.user_id)
    await session.commit()
    return _grant_dict(grant, display_name="LINE 志工" if user is None else user.display_name)


@router.get("/v1/organizations/{organizationId}/volunteer-notifications")
async def list_volunteer_notification_failures(
    organizationId: UUID,  # noqa: N803
    event_type: str | None = None,
    notification_status: str | None = Query(default=None, alias="status"),
    failed_from: datetime | None = None,
    failed_to: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> dict:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_notification_delivery",
    ):
        repository = VolunteerAccessRepository(session, organizationId)
        deliveries = await repository.list_notifications(
            event_type=event_type,
            status=notification_status,
            failed_from=failed_from,
            failed_to=failed_to,
            cursor=_decode_application_cursor(cursor),
            limit=limit + 1,
        )
        identities = AuthenticationRepository(session)
        page_deliveries = deliveries[:limit]
        items = []
        for delivery in page_deliveries:
            user = await identities.get_user(delivery.user_id)
            items.append(
                {
                    "id": delivery.id,
                    "organization_id": delivery.organization_id,
                    "recipient_display_name": ("LINE 志工" if user is None else user.display_name),
                    "event_type": delivery.event_type,
                    "resource_type": delivery.resource_type,
                    "resource_id": delivery.resource_id,
                    "status": delivery.status,
                    "attempt_count": delivery.attempt_count,
                    "last_error_code": delivery.last_error_code,
                    "last_failed_at": delivery.last_failed_at,
                    "updated_at": delivery.updated_at,
                }
            )
    await session.commit()
    return {
        "items": items,
        "next_cursor": (
            _encode_notification_cursor(page_deliveries[-1]) if len(deliveries) > limit else None
        ),
    }


@router.post("/v1/organizations/{organizationId}/volunteer-notifications/retry")
async def retry_volunteer_notifications(
    organizationId: UUID,  # noqa: N803
    payload: VolunteerNotificationRetryRequest,
    response: Response,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> dict:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_notification_retry_batch",
    ) as normalized_support_reason:
        repository = VolunteerAccessRepository(session, organizationId)
        existing = await repository.retry_batch_by_operation(payload.operation_id)
        batch, items = await VolunteerNotificationService(repository).retry_failed(
            operation_id=payload.operation_id,
            notification_ids=payload.notification_ids,
            actor_user_id=context.user_id,
            platform_support_reason=normalized_support_reason,
        )
    await session.commit()
    response.status_code = status.HTTP_200_OK if existing is not None else status.HTTP_202_ACCEPTED
    return {
        "id": batch.id,
        "operation_id": batch.operation_id,
        "requested_count": batch.requested_count,
        "requeued_count": batch.requeued_count,
        "conflict_count": batch.conflict_count,
        "failed_count": sum(item.result == "failed" for item in items),
        "items": [
            {
                "notification_id": item.notification_delivery_id,
                "result": item.result,
                "error_code": item.error_code,
            }
            for item in items
        ],
    }


@router.post("/v1/organizations/{organizationId}/volunteer-decision-batches")
async def create_volunteer_decision_batch(
    organizationId: UUID,  # noqa: N803
    payload: VolunteerDecisionBatchRequest,
    response: Response,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> dict:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_decision_batch",
    ) as normalized_support_reason:
        repository = VolunteerAccessRepository(session, organizationId)
        existing = await repository.batch_by_operation(payload.operation_id)
        if isinstance(payload.selection, ExplicitVolunteerDecisionSelection):
            explicit_items = [
                (item.application_id, item.expected_version) for item in payload.selection.items
            ]
            filters = None
            overrides = payload.selection.items
        else:
            explicit_items = None
            filters = payload.selection.filter.model_dump(exclude_none=True)
            overrides = payload.selection.overrides
        batch, items = await VolunteerBatchService(repository).create_snapshot(
            actor_user_id=context.user_id,
            operation_id=payload.operation_id,
            decision=payload.decision,
            selection_mode=payload.selection.mode,
            explicit_items=explicit_items,
            filters=filters,
            request_payload=payload.model_dump(mode="json"),
            reason=payload.reason,
            platform_support_reason=normalized_support_reason,
            default_valid_from=payload.default_valid_from,
            default_expires_at=payload.default_expires_at,
        )
        override_map = {item.application_id: item for item in overrides}
        for item in items:
            override = override_map.get(item.application_id)
            if override is not None:
                item.override_valid_from = override.valid_from
                item.override_expires_at = override.expires_at
    await session.commit()
    response.status_code = status.HTTP_200_OK if existing is not None else status.HTTP_201_CREATED
    return _batch_dict(batch)


@router.get("/v1/organizations/{organizationId}/volunteer-decision-batches/{batchId}")
async def get_volunteer_decision_batch(
    organizationId: UUID,  # noqa: N803
    batchId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> dict:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_decision_batch",
    ):
        batch = await VolunteerAccessRepository(session, organizationId).batch(batchId)
        if batch is None:
            raise DomainError("batch_not_found", "找不到此批次", 404)
    await session.commit()
    return _batch_dict(batch)


@router.get("/v1/organizations/{organizationId}/volunteer-decision-batches/{batchId}/items")
async def list_volunteer_decision_batch_items(
    organizationId: UUID,  # noqa: N803
    batchId: UUID,  # noqa: N803
    item_result: str | None = Query(default=None, alias="result"),
    cursor: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> dict:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_decision_batch_item",
    ):
        repository = VolunteerAccessRepository(session, organizationId)
        if await repository.batch(batchId) is None:
            raise DomainError("batch_not_found", "找不到此批次", 404)
        items = await repository.batch_items_after(
            batchId, cursor, result=item_result, limit=limit + 1
        )
    await session.commit()
    has_more = len(items) > limit
    page_items = items[:limit]
    return {
        "items": [
            {
                "id": item.id,
                "application_id": item.application_id,
                "expected_version": item.expected_version,
                "result": item.result,
                "error_code": item.error_code,
                "resulting_application_version": item.resulting_application_version,
                "membership_id": item.membership_id,
                "grant_id": item.grant_id,
                "processed_at": item.processed_at,
            }
            for item in page_items
        ],
        "next_cursor": str(page_items[-1].id) if has_more else None,
    }
