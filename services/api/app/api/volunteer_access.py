from __future__ import annotations

import base64
import binascii
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    decode_platform_support_reason,
    platform_support_audit_lifecycle,
    request_session,
    validate_platform_support_request,
)
from services.api.app.api.errors import DomainError, ErrorResponse
from services.api.app.application.audit_service import AuditService
from services.api.app.application.ports.authentication import LineIdentityVerifierPort
from services.api.app.application.volunteer_access_service import (
    VolunteerAccessService,
    VolunteerApplicationDetailResult,
    VolunteerStatusResult,
)
from services.api.app.application.volunteer_batch_service import VolunteerBatchService
from services.api.app.application.volunteer_notification_service import (
    VolunteerNotificationService,
)
from services.api.app.application.volunteer_pii_service import VolunteerPiiService
from services.api.app.config.settings import get_settings
from services.api.app.domain.tenant_context import TenantContext
from services.api.app.domain.volunteer_access import validate_service_date_selection
from services.api.app.domain.volunteer_target import (
    EntryTarget,
    OrganizationTarget,
    VolunteerTarget,
    build_volunteer_target,
)
from services.api.app.infrastructure.line.identity_verification_adapter import (
    configured_line_identity_verifier,
)
from services.api.app.infrastructure.security.pii_cipher import (
    configured_pii_cipher_from_settings,
)
from services.api.app.infrastructure.security.pii_reveal_audit import (
    CommittedPiiRevealAuditor,
    TransactionalPiiCollectionAuditor,
)
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import (
    set_organization_scope,
    set_platform_support_scope,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.organization_repository import (
    OrganizationRepository,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    tags=["Volunteer Applications"],
    responses={
        401: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)

ApplicationStatus = Literal["pending", "approved", "rejected", "withdrawn"]
EffectiveAccessStatus = Literal[
    "none",
    "pending",
    "upcoming",
    "active",
    "expired",
    "revoked",
    "rejected",
    "withdrawn",
]
GrantStatus = Literal["active", "expired", "revoked"]
NextAction = Literal[
    "apply",
    "wait",
    "withdraw",
    "enter_care",
    "reapply",
    "contact_shelter",
    "return_to_line",
]


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
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["organization_id"],
                    "properties": {
                        "organization_id": {"type": "string", "format": "uuid"},
                        "shelter_entry_reference": {"type": "null"},
                    },
                },
                {
                    "required": ["shelter_entry_reference"],
                    "properties": {
                        "organization_id": {"type": "null"},
                        "shelter_entry_reference": {
                            "type": "string",
                            "minLength": 32,
                            "maxLength": 512,
                            "pattern": r"^[A-Za-z0-9._~-]+$",
                        },
                    },
                },
            ]
        },
    )

    id_token: str = Field(min_length=1)
    organization_id: UUID | None = None
    shelter_entry_reference: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> VolunteerIdentityRequest:
        try:
            build_volunteer_target(
                organization_id=self.organization_id,
                shelter_entry_reference=self.shelter_entry_reference,
            )
        except DomainError as exc:
            raise ValueError(exc.code) from exc
        return self

    @property
    def target(self) -> VolunteerTarget:
        return build_volunteer_target(
            organization_id=self.organization_id,
            shelter_entry_reference=self.shelter_entry_reference,
        )


class VolunteerEntryIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=1)
    shelter_entry_reference: str = Field(
        min_length=32,
        max_length=512,
        pattern=r"^[A-Za-z0-9._~-]+$",
    )

    @model_validator(mode="after")
    def validate_entry_target(self) -> VolunteerEntryIdentityRequest:
        try:
            build_volunteer_target(
                organization_id=None,
                shelter_entry_reference=self.shelter_entry_reference,
            )
        except DomainError as exc:
            raise ValueError(exc.code) from exc
        return self


class VolunteerApplicationCreateRequest(VolunteerIdentityRequest):
    applicant_name: str = Field(min_length=1, max_length=200)
    phone_number: str = Field(min_length=1, max_length=50)
    basic_profile: dict[str, Any] | None = None
    insurance_identity: str | None = Field(default=None, max_length=128)
    insurance_consent_acknowledged: bool = False
    client_request_id: UUID
    consent_acknowledged: Literal[True]
    service_dates: list[date] = Field(min_length=1, max_length=14)

    @model_validator(mode="after")
    def validate_service_dates(self) -> VolunteerApplicationCreateRequest:
        validate_service_date_selection(self.service_dates, today=date.today())
        return self


class VolunteerApplicationWithdrawRequest(VolunteerEntryIdentityRequest):
    expected_version: int = Field(ge=1)


class PublicOrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    applications_enabled: bool
    insurance_required: bool


class PublicVolunteerOrganizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    code: str
    name: str
    service_area: str | None
    insurance_required: bool


class VolunteerApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    display_name: str
    status: ApplicationStatus
    submitted_at: datetime
    decided_at: datetime | None = None
    decision_reason: str | None = None
    version: int = Field(ge=1)


class VolunteerGrantSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: GrantStatus
    source_type: Literal["manager_approval", "legacy_migration"]
    policy_version_used: int | None = Field(default=None, ge=1)
    duration_hours_used: int | None = Field(default=None, ge=1)
    valid_from: datetime
    expires_at: datetime
    version: int = Field(ge=1)


class VolunteerApplicationStatusResponse(BaseModel):
    organization: PublicOrganizationResponse
    application: VolunteerApplicationResponse | None = None
    grant: VolunteerGrantSummaryResponse | None = None
    effective_status: EffectiveAccessStatus
    next_actions: list[NextAction]


class VolunteerServiceDateAvailabilityResponse(BaseModel):
    service_date: date
    pending_count: int = Field(ge=1)


class VolunteerApplicationServiceDate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_date: date
    status: Literal["pending", "approved", "rejected", "withdrawn"]
    decided_at: datetime | None = None
    decision_reason: str | None = None
    version: int = Field(ge=1)


class VolunteerApplicationListResponse(BaseModel):
    items: list[VolunteerApplicationResponse]
    matching_count: int = Field(ge=0)
    next_cursor: str | None
    available_service_dates: list[VolunteerServiceDateAvailabilityResponse]


class VolunteerApplicationDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    display_name: str
    status: ApplicationStatus
    submitted_at: datetime
    decided_at: datetime | None = None
    decision_reason: str | None = None
    version: int = Field(ge=1)
    service_dates: list[VolunteerApplicationServiceDate]


class VolunteerPiiRevealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose_code: Literal["application_review"]


class VolunteerPiiRevealResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicant_name: str
    phone_number: str
    basic_profile: dict[str, str] | None


class VolunteerAccessGrant(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    membership_id: UUID
    application_id: UUID
    display_name: str
    status: GrantStatus
    source_type: Literal["manager_approval", "legacy_migration"]
    policy_version_used: int | None = Field(default=None, ge=1)
    duration_hours_used: int | None = Field(default=None, ge=1)
    valid_from: datetime
    expires_at: datetime
    approved_at: datetime
    revocation_reason: str | None = None
    version: int = Field(ge=1)
    notification: VolunteerNotification | None = None


class VolunteerAccessGrantListResponse(BaseModel):
    items: list[VolunteerAccessGrant]
    next_cursor: str | None


BatchStatus = Literal["queued", "processing", "completed", "completed_with_errors"]
BatchItemResult = Literal["pending", "succeeded", "conflict", "failed"]


class VolunteerDecisionBatchResponse(BaseModel):
    id: UUID
    organization_id: UUID
    operation_id: UUID
    decision: Literal["approve", "reject"]
    selection_mode: Literal["explicit_items", "all_filtered"]
    snapshot_at: datetime
    policy_version_used: int | None = Field(default=None, ge=1)
    default_duration_hours_used: int | None = Field(default=None, ge=1)
    status: BatchStatus
    requested_count: int = Field(ge=1)
    processed_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    chunk_size: Literal[500]
    created_at: datetime
    completed_at: datetime | None = None


class VolunteerDecisionItemResponse(BaseModel):
    application_id: UUID
    expected_version: int = Field(ge=1)
    result: BatchItemResult
    error_code: str | None = None
    resulting_application_version: int | None = Field(default=None, ge=1)
    membership_id: UUID | None = None
    grant_id: UUID | None = None
    grant: VolunteerGrantSummaryResponse | None = None


class VolunteerDecisionBatchItemListResponse(BaseModel):
    items: list[VolunteerDecisionItemResponse]
    next_cursor: str | None


NotificationStatus = Literal["pending", "sending", "retry_wait", "sent", "failed"]
NotificationFailureStatus = Literal["retry_wait", "failed"]
NotificationEventType = Literal[
    "application_submitted",
    "application_withdrawn",
    "approved",
    "rejected",
    "grant_changed",
    "expired",
    "revoked",
]


class VolunteerNotification(BaseModel):
    id: UUID
    organization_id: UUID
    recipient_display_name: str
    event_type: NotificationEventType
    resource_type: Literal["volunteer_application", "volunteer_access_grant"]
    resource_id: UUID
    status: NotificationStatus
    attempt_count: int = Field(ge=0)
    last_error_code: str | None = None
    last_failed_at: datetime | None = None
    updated_at: datetime


VolunteerAccessGrant.model_rebuild()


class VolunteerNotificationListResponse(BaseModel):
    items: list[VolunteerNotification]
    next_cursor: str | None


class VolunteerNotificationRetryItem(BaseModel):
    notification_id: UUID
    result: Literal["requeued", "conflict", "failed"]
    error_code: str | None = None


class VolunteerNotificationRetryResponse(BaseModel):
    id: UUID
    operation_id: UUID
    requested_count: int = Field(ge=1)
    requeued_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    items: list[VolunteerNotificationRetryItem]


class VolunteerAccessPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: UUID
    applications_enabled: bool
    default_grant_duration_hours: int = Field(ge=1)
    daily_application_limit: int = Field(ge=1)
    version: int = Field(ge=1)


class VolunteerAccessPolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 2})

    expected_version: int = Field(ge=1)
    applications_enabled: bool = Field(default=None)
    default_grant_duration_hours: int = Field(default=None, ge=1)
    daily_application_limit: int = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_update_fields(self) -> VolunteerAccessPolicyUpdateRequest:
        if not {
            "applications_enabled",
            "default_grant_duration_hours",
            "daily_application_limit",
        } & self.model_fields_set:
            raise ValueError("at least one policy field is required")
        return self


class VolunteerDecisionItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: UUID
    expected_version: int = Field(ge=1)
    valid_from: datetime | None = None
    expires_at: datetime | None = None


class ExplicitVolunteerDecisionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["explicit_items"]
    service_date: date | None
    items: list[VolunteerDecisionItemRequest] = Field(
        min_length=1, max_length=500, json_schema_extra={"uniqueItems": True}
    )

    @model_validator(mode="after")
    def validate_unique_items(self) -> ExplicitVolunteerDecisionSelection:
        if len({item.application_id for item in self.items}) != len(self.items):
            raise ValueError("duplicate application_id")
        return self


class VolunteerApplicationBatchFilter(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["service_date"],
                    "properties": {
                        "service_date": {"type": "string", "format": "date"},
                        "unassigned": {"const": False},
                    },
                },
                {
                    "required": ["unassigned"],
                    "properties": {
                        "service_date": {"type": "null"},
                        "unassigned": {"const": True},
                    },
                },
            ]
        },
    )

    status: Literal["pending"]
    service_date: date | None = None
    unassigned: bool = False
    submitted_from: datetime | None = None
    submitted_to: datetime | None = None

    @model_validator(mode="after")
    def validate_date_scope(self) -> VolunteerApplicationBatchFilter:
        if (self.service_date is None) == (not self.unassigned):
            raise ValueError("exactly one review date scope is required")
        return self

    def to_repository_filters(self) -> dict:
        return self.model_dump(exclude_none=True)


class AllFilteredVolunteerDecisionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["all_filtered"]
    filter: VolunteerApplicationBatchFilter
    overrides: list[VolunteerDecisionItemRequest] = Field(
        default_factory=list, max_length=500, json_schema_extra={"uniqueItems": True}
    )

    @model_validator(mode="after")
    def validate_unique_overrides(self) -> AllFilteredVolunteerDecisionSelection:
        if len({item.application_id for item in self.overrides}) != len(self.overrides):
            raise ValueError("duplicate application_id")
        return self


class VolunteerDecisionBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    default_valid_from: datetime | None = None
    default_expires_at: datetime | None = None
    selection: Annotated[
        ExplicitVolunteerDecisionSelection | AllFilteredVolunteerDecisionSelection,
        Field(discriminator="mode"),
    ]


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
    notification_ids: list[UUID] = Field(
        min_length=1, max_length=500, json_schema_extra={"uniqueItems": True}
    )

    @model_validator(mode="after")
    def validate_unique_notification_ids(self) -> VolunteerNotificationRetryRequest:
        if len(set(self.notification_ids)) != len(self.notification_ids):
            raise ValueError("duplicate notification_id")
        return self


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
        channel_id=settings.line_login_channel_id or settings.line_channel_id,
    )


def get_volunteer_pii_service() -> VolunteerPiiService:
    return VolunteerPiiService(
        configured_pii_cipher_from_settings(get_settings()),
        collection_auditor=TransactionalPiiCollectionAuditor(),
    )


async def _service_for_entry(
    session: AsyncSession,
    raw_reference: str,
    verifier: LineIdentityVerifierPort,
    pii_service: VolunteerPiiService | None = None,
) -> tuple[VolunteerAccessService, UUID]:
    VolunteerAccessService.validate_entry_reference(raw_reference)
    resolved = await VolunteerAccessRepository.resolve_and_scope(session, raw_reference)
    if resolved is None:
        raise DomainError("entry_unavailable", "此志工入口目前無法使用", 403)
    reference_id, organization_id, *_public_context = resolved
    repository = VolunteerAccessRepository(session, organization_id)
    return (
        VolunteerAccessService(
            repository,
            AuthenticationRepository(session),
            verifier,
            audit=AuditService(session),
            notifications=VolunteerNotificationService(repository),
            pii_service=pii_service,
        ),
        reference_id,
    )


async def _service_for_target(
    session: AsyncSession,
    payload: VolunteerIdentityRequest,
    verifier: LineIdentityVerifierPort,
    verified_line_user_id: str | None = None,
    *,
    for_submit: bool = False,
    pii_service: VolunteerPiiService | None = None,
) -> tuple[VolunteerAccessService, UUID | None, str | None]:
    verified_line_user_id = (
        verified_line_user_id
        if verified_line_user_id is not None
        else await verifier.verify(payload.id_token)
    )
    target = payload.target
    if isinstance(target, OrganizationTarget):
        await set_organization_scope(session, target.organization_id)
        repository = VolunteerAccessRepository(session, target.organization_id)
        service_factory = (
            VolunteerAccessService.for_organization
            if for_submit
            else VolunteerAccessService.for_organization_status
        )
        if for_submit:
            service = await service_factory(
                target.organization_id,
                repository,
                AuthenticationRepository(session),
                verifier,
                audit=AuditService(session),
                notifications=VolunteerNotificationService(repository),
                pii_service=pii_service,
            )
        else:
            service = await service_factory(
                target.organization_id,
                repository,
                AuthenticationRepository(session),
                verifier,
                audit=AuditService(session),
                notifications=VolunteerNotificationService(repository),
            )
        return service, None, verified_line_user_id
    assert isinstance(target, EntryTarget)
    if for_submit and pii_service is not None and hasattr(pii_service, "create_profile"):
        service, reference_id = await _service_for_entry(
            session, target.shelter_entry_reference, verifier, pii_service=pii_service
        )
    else:
        service, reference_id = await _service_for_entry(
            session, target.shelter_entry_reference, verifier
        )
    return service, reference_id, verified_line_user_id


def _legacy_entry_reference(payload: VolunteerEntryIdentityRequest) -> str:
    return payload.shelter_entry_reference


def _response(result: VolunteerStatusResult) -> VolunteerApplicationStatusResponse:
    return VolunteerApplicationStatusResponse.model_validate(
        {
            "organization": result.organization,
            "application": None
            if result.application is None
            else _application_dict(result.application),
            "grant": result.grant,
            "effective_status": result.effective_status,
            "next_actions": result.next_actions,
        }
    )


@router.post(
    "/v1/volunteer-applications/status",
    response_model=VolunteerApplicationStatusResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    openapi_extra={"security": []},
)
async def resolve_volunteer_application_status(
    payload: VolunteerIdentityRequest,
    session: AsyncSession = Depends(request_session),  # noqa: B008
    verifier: LineIdentityVerifierPort = Depends(get_line_identity_verifier),  # noqa: B008
) -> VolunteerApplicationStatusResponse:
    try:
        verified_line_user_id = await verifier.verify(payload.id_token)
        service, target_id, verified_line_user_id = await _service_for_target(
            session, payload, verifier, verified_line_user_id
        )
        result = await service.status(
            id_token=payload.id_token,
            entry_reference_id=target_id,
            verified_line_user_id=verified_line_user_id,
        )
    except SQLAlchemyError as exc:
        raise DomainError("dependency_unavailable", "志工申請狀態暫時無法使用", 503) from exc
    return _response(result)


@router.post(
    "/v1/volunteer-applications",
    response_model=VolunteerApplicationStatusResponse,
    responses={
        201: {"model": VolunteerApplicationStatusResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    openapi_extra={"security": []},
)
async def submit_volunteer_application(
    payload: VolunteerApplicationCreateRequest,
    response: Response,
    session: AsyncSession = Depends(request_session),  # noqa: B008
    verifier: LineIdentityVerifierPort = Depends(get_line_identity_verifier),  # noqa: B008
    pii_service: VolunteerPiiService = Depends(get_volunteer_pii_service),  # noqa: B008
) -> VolunteerApplicationStatusResponse:
    try:
        verified_line_user_id = await verifier.verify(payload.id_token)
        service, reference_id, verified_line_user_id = await _service_for_target(
            session,
            payload,
            verifier,
            verified_line_user_id,
            for_submit=True,
            pii_service=pii_service,
        )
        result = await service.submit(
            id_token=payload.id_token,
            entry_reference_id=reference_id,
            organization_id=payload.organization_id,
            verified_line_user_id=verified_line_user_id,
            client_request_id=payload.client_request_id,
            consent_acknowledged=payload.consent_acknowledged,
            applicant_name=payload.applicant_name,
            phone_number=payload.phone_number,
            basic_profile=payload.basic_profile,
            insurance_identity=payload.insurance_identity,
            insurance_consent_acknowledged=payload.insurance_consent_acknowledged,
            service_dates=payload.service_dates,
        )
        response_body = _response(result.status)
        await session.commit()
    except SQLAlchemyError as exc:
        raise DomainError("dependency_unavailable", "志工申請暫時無法使用", 503) from exc
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return response_body


@router.post(
    "/v1/volunteer-applications/{applicationId}/withdraw",
    response_model=VolunteerApplicationStatusResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    openapi_extra={"security": []},
)
async def withdraw_volunteer_application(
    applicationId: UUID,  # noqa: N803
    payload: VolunteerApplicationWithdrawRequest,
    session: AsyncSession = Depends(request_session),  # noqa: B008
    verifier: LineIdentityVerifierPort = Depends(get_line_identity_verifier),  # noqa: B008
) -> VolunteerApplicationStatusResponse:
    try:
        verified_line_user_id = await verifier.verify(payload.id_token)
        entry_reference = _legacy_entry_reference(payload)
        service, reference_id = await _service_for_entry(session, entry_reference, verifier)
        result = await service.withdraw(
            id_token=payload.id_token,
            entry_reference_id=reference_id,
            verified_line_user_id=verified_line_user_id,
            application_id=applicationId,
            expected_version=payload.expected_version,
        )
        response_body = _response(result)
        await session.commit()
    except SQLAlchemyError as exc:
        raise DomainError("dependency_unavailable", "志工申請暫時無法使用", 503) from exc
    return response_body


@router.get(
    "/v1/public/volunteer-organizations",
    response_model=list[PublicVolunteerOrganizationResponse],
    responses={503: {"model": ErrorResponse}},
    openapi_extra={"security": []},
)
async def list_public_volunteer_organizations(
    session: AsyncSession = Depends(request_session),  # noqa: B008
) -> list[PublicVolunteerOrganizationResponse]:
    try:
        rows = await OrganizationRepository(session).list_public_volunteer_organizations()
    except SQLAlchemyError as exc:
        raise DomainError(
            "dependency_unavailable",
            "公開收容所清單暫時無法使用",
            503,
        ) from exc
    return [
        PublicVolunteerOrganizationResponse(
            id=organization_id,
            code=code,
            name=name,
            service_area=service_area,
            insurance_required=insurance_required,
        )
        for organization_id, code, name, service_area, insurance_required in rows
    ]


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


def _application_detail_dict(detail: VolunteerApplicationDetailResult) -> dict:
    application = detail.application
    return {
        **_application_dict(application),
        "service_dates": [
            {
                "service_date": item.service_date,
                "status": item.status,
                "decided_at": item.decided_at,
                "decision_reason": item.decision_reason,
                "version": item.version,
            }
            for item in detail.service_dates
        ],
    }


def _tenant_context(context: RequestContext) -> TenantContext:
    return TenantContext(
        user_id=context.user_id,
        organization_id=context.organization_id,
        role=context.role,
        platform_scope=context.platform_scope,
    )


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
        "policy_version_used": batch.policy_version_used,
        "default_duration_hours_used": batch.default_duration_hours_used,
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
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    openapi_extra={"security": [{"bearerAuth": []}]},
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
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    openapi_extra={"security": [{"bearerAuth": []}]},
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
            daily_application_limit=payload.daily_application_limit,
        )
    response_body = _policy_response(policy)
    await session.commit()
    return response_body


@router.get(
    "/v1/organizations/{organizationId}/volunteer-applications",
    response_model=VolunteerApplicationListResponse,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    openapi_extra={"security": [{"bearerAuth": []}]},
)
async def list_volunteer_applications(
    organizationId: UUID,  # noqa: N803
    application_status: ApplicationStatus | None = Query(default=None, alias="status"),  # noqa: B008
    service_date: date | None = None,
    unassigned: bool = False,
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
            service_date=service_date,
            unassigned=unassigned,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
            cursor=_decode_application_cursor(cursor),
            limit=limit + 1,
        )
        matching_count = await repository.count_applications(
            status=application_status,
            service_date=service_date,
            unassigned=unassigned,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
        )
        available_service_dates = await repository.pending_service_date_counts()
    await session.commit()
    has_more = len(items) > limit
    page_items = items[:limit]
    return {
        "items": [_application_dict(item) for item in page_items],
        "matching_count": matching_count,
        "next_cursor": _encode_application_cursor(page_items[-1]) if has_more else None,
        "available_service_dates": [
            {"service_date": value, "pending_count": count}
            for value, count in available_service_dates
        ],
    }


@router.get(
    "/v1/organizations/{organizationId}/volunteer-applications/{applicationId}",
    response_model=VolunteerApplicationDetailResponse,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    openapi_extra={"security": [{"bearerAuth": []}]},
)
async def get_volunteer_application_detail(
    organizationId: UUID,  # noqa: N803
    applicationId: UUID,  # noqa: N803
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> VolunteerApplicationDetailResponse:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_application_detail",
    ):
        repository = VolunteerAccessRepository(session, organizationId)
        detail = await _management_service(session, repository).application_detail(
            applicationId,
            tenant_context=_tenant_context(context),
        )
    await session.commit()
    return VolunteerApplicationDetailResponse.model_validate(_application_detail_dict(detail))


@router.post(
    "/v1/organizations/{organizationId}/volunteer-applications/{applicationId}/pii-reveal",
    response_model=VolunteerPiiRevealResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    openapi_extra={"security": [{"bearerAuth": []}]},
)
async def reveal_volunteer_application_pii(
    organizationId: UUID,  # noqa: N803
    applicationId: UUID,  # noqa: N803
    payload: VolunteerPiiRevealRequest,
    context: RequestContext = Depends(current_request_context),  # noqa: B008
    session: AsyncSession = Depends(request_session),  # noqa: B008
    pii_service: VolunteerPiiService = Depends(get_volunteer_pii_service),  # noqa: B008
    support_reason: str | None = Header(default=None, alias="X-Platform-Support-Reason"),
) -> VolunteerPiiRevealResponse:
    async with volunteer_management_scope(
        session=session,
        context=context,
        organization_id=organizationId,
        support_reason=support_reason,
        resource_type="volunteer_application_pii_reveal",
    ):
        repository = VolunteerAccessRepository(session, organizationId)
        policy = await repository.policy()
        revealed = await pii_service.reveal_profile(
            repository=repository,
            application_id=applicationId,
            tenant_context=_tenant_context(context),
            purpose_code=payload.purpose_code,
            request_id=uuid4(),
            policy_version=f"organization-policy-v{policy.version}",
            now=datetime.now(timezone.utc),
            audit=CommittedPiiRevealAuditor(session_factory),
        )
    await session.commit()
    return VolunteerPiiRevealResponse(
        applicant_name=revealed.applicant_name,
        phone_number=revealed.phone_number,
        basic_profile=revealed.basic_profile,
    )


@router.get(
    "/v1/organizations/{organizationId}/volunteer-access-grants",
    response_model=VolunteerAccessGrantListResponse,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    openapi_extra={"security": [{"bearerAuth": []}]},
)
async def list_volunteer_access_grants(
    organizationId: UUID,  # noqa: N803
    grant_status: GrantStatus | None = Query(default=None, alias="status"),  # noqa: B008
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


@router.patch(
    "/v1/organizations/{organizationId}/volunteer-access-grants/{grantId}",
    response_model=VolunteerAccessGrant,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    openapi_extra={"security": [{"bearerAuth": []}]},
)
async def update_volunteer_access_grant(
    organizationId: UUID,  # noqa: N803
    grantId: UUID,  # noqa: N803
    payload: Annotated[
        GrantPeriodUpdateRequest | GrantRevokeRequest,
        Field(discriminator="action"),
    ],
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
    response_body = VolunteerAccessGrant.model_validate(
        _grant_dict(grant, display_name="LINE 志工" if user is None else user.display_name)
    )
    await session.commit()
    return response_body


@router.get(
    "/v1/organizations/{organizationId}/volunteer-notifications",
    response_model=VolunteerNotificationListResponse,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    openapi_extra={"security": [{"bearerAuth": []}]},
)
async def list_volunteer_notification_failures(
    organizationId: UUID,  # noqa: N803
    event_type: NotificationEventType | None = None,
    notification_status: NotificationFailureStatus | None = Query(default=None, alias="status"),  # noqa: B008
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
    response_body = VolunteerNotificationListResponse.model_validate(
        {
            "items": items,
            "next_cursor": (
                _encode_notification_cursor(page_deliveries[-1])
                if len(deliveries) > limit
                else None
            ),
        }
    )
    await session.commit()
    return response_body


@router.post(
    "/v1/organizations/{organizationId}/volunteer-notifications/retry",
    response_model=VolunteerNotificationRetryResponse,
    responses={
        202: {"model": VolunteerNotificationRetryResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    openapi_extra={"security": [{"bearerAuth": []}]},
)
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
    response_body = VolunteerNotificationRetryResponse.model_validate(
        {
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
    )
    await session.commit()
    response.status_code = status.HTTP_200_OK if existing is not None else status.HTTP_202_ACCEPTED
    return response_body


@router.post(
    "/v1/organizations/{organizationId}/volunteer-decision-batches",
    response_model=VolunteerDecisionBatchResponse,
    responses={
        201: {"model": VolunteerDecisionBatchResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    openapi_extra={"security": [{"bearerAuth": []}]},
)
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
            filters = {"service_date": payload.selection.service_date}
            overrides = payload.selection.items
        else:
            explicit_items = None
            filters = payload.selection.filter.to_repository_filters()
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
    response_body = VolunteerDecisionBatchResponse.model_validate(_batch_dict(batch))
    await session.commit()
    response.status_code = status.HTTP_200_OK if existing is not None else status.HTTP_201_CREATED
    return response_body


@router.get(
    "/v1/organizations/{organizationId}/volunteer-decision-batches/{batchId}",
    response_model=VolunteerDecisionBatchResponse,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    openapi_extra={"security": [{"bearerAuth": []}]},
)
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


@router.get(
    "/v1/organizations/{organizationId}/volunteer-decision-batches/{batchId}/items",
    response_model=VolunteerDecisionBatchItemListResponse,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    openapi_extra={"security": [{"bearerAuth": []}]},
)
async def list_volunteer_decision_batch_items(
    organizationId: UUID,  # noqa: N803
    batchId: UUID,  # noqa: N803
    item_result: BatchItemResult | None = Query(default=None, alias="result"),  # noqa: B008
    cursor: str = Query(default=None),  # noqa: B008
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
