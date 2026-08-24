"""Volunteer self-service application and own-status workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.ports.authentication import LineIdentityVerifierPort
from services.api.app.application.volunteer_notification_service import (
    VolunteerNotificationService,
)
from services.api.app.application.volunteer_pii_service import VolunteerPiiService
from services.api.app.domain.volunteer_access import (
    normalize_reason,
    snapshot_policy,
    transition_application,
    validate_grant_period,
    validate_service_date_selection,
)
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    OrganizationMembership,
    User,
)
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerAccessGrant,
    VolunteerApplication,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)


@dataclass(frozen=True)
class PublicOrganizationResult:
    id: UUID
    name: str
    applications_enabled: bool
    insurance_required: bool


@dataclass(frozen=True)
class VolunteerStatusResult:
    organization: PublicOrganizationResult
    application: VolunteerApplication | None
    grant: VolunteerAccessGrant | None
    effective_status: str
    next_actions: list[str]


@dataclass(frozen=True)
class VolunteerSubmitResult:
    status: VolunteerStatusResult
    created: bool


def effective_application_status(
    application: VolunteerApplication | None,
    grant: VolunteerAccessGrant | None,
    *,
    now: datetime | None = None,
) -> tuple[str, list[str]]:
    clock = now or datetime.now(timezone.utc)
    if application is None:
        return "none", ["apply"]
    if application.status == "pending":
        return "pending", ["wait", "withdraw"]
    if application.status == "rejected":
        return "rejected", ["reapply", "contact_shelter"]
    if application.status == "withdrawn":
        return "withdrawn", ["reapply"]
    if grant is None:
        return "none", ["contact_shelter"]
    if grant.status == "revoked":
        return "revoked", ["reapply", "contact_shelter"]
    if grant.status == "expired" or clock >= grant.expires_at:
        return "expired", ["reapply"]
    if clock < grant.valid_from:
        return "upcoming", ["wait"]
    return "active", ["enter_care"]


def grant_remaining_seconds(
    grant: VolunteerAccessGrant | None, *, now: datetime | None = None
) -> int | None:
    if grant is None:
        return None
    clock = now or datetime.now(timezone.utc)
    return max(0, int((grant.expires_at - clock).total_seconds()))


class VolunteerAccessService:
    def __init__(
        self,
        repository: VolunteerAccessRepository,
        identities: AuthenticationRepository,
        verifier: LineIdentityVerifierPort,
        *,
        audit: AuditService | None = None,
        notifications: VolunteerNotificationService | None = None,
        pii_service: VolunteerPiiService | None = None,
    ) -> None:
        self.repository = repository
        self.identities = identities
        self.verifier = verifier
        self.audit = audit
        self.notifications = notifications
        self.pii_service = pii_service

    @classmethod
    async def for_organization(
        cls,
        organization_id: UUID,
        repository: VolunteerAccessRepository,
        identities: AuthenticationRepository,
        verifier: LineIdentityVerifierPort,
        *,
        audit: AuditService | None = None,
        notifications: VolunteerNotificationService | None = None,
        pii_service: VolunteerPiiService | None = None,
    ) -> VolunteerAccessService:
        """Resolve and validate one organization-scoped volunteer service.

        The organization ID selects the target, but the database remains the
        source of truth for its active state and display data.  The repository
        is checked before any lookup so a service can never be built around a
        repository scoped to a different tenant.
        """
        if (
            not isinstance(organization_id, UUID)
            or getattr(repository, "organization_id", None) != organization_id
        ):
            raise DomainError("organization_scope_mismatch", "收容所資料範圍不符", 404)

        organization = await identities.get_organization(organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("entry_unavailable", "此志工入口目前無法使用", 403)

        policy = await repository.policy()
        if not policy.applications_enabled:
            raise DomainError(
                "volunteer_applications_disabled",
                "此收容所目前暫停接受新申請",
                403,
            )

        return cls(
            repository,
            identities,
            verifier,
            audit=audit,
            notifications=notifications,
            pii_service=pii_service,
        )

    @classmethod
    async def for_organization_status(
        cls,
        organization_id: UUID,
        repository: VolunteerAccessRepository,
        identities: AuthenticationRepository,
        verifier: LineIdentityVerifierPort,
        *,
        audit: AuditService | None = None,
        notifications: VolunteerNotificationService | None = None,
        pii_service: VolunteerPiiService | None = None,
    ) -> VolunteerAccessService:
        """Build an organization-scoped service for status reads only.

        Status remains readable for an active organization when its policy
        disables new applications.  The submit factory above intentionally
        keeps the applications-enabled gate.
        """
        if (
            not isinstance(organization_id, UUID)
            or getattr(repository, "organization_id", None) != organization_id
        ):
            raise DomainError("organization_scope_mismatch", "收容所資料範圍不符", 404)

        organization = await identities.get_organization(organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("entry_unavailable", "此志工入口目前無法使用", 403)
        await repository.policy()
        return cls(
            repository,
            identities,
            verifier,
            audit=audit,
            notifications=notifications,
            pii_service=pii_service,
        )

    @staticmethod
    def validate_entry_reference(raw_reference: str) -> str:
        normalized = raw_reference.strip()
        if not normalized:
            raise DomainError("entry_reference_required", "缺少收容所志工入口", 422)
        return normalized

    async def _public_organization(self) -> PublicOrganizationResult:
        policy = await self.repository.policy()
        organization = await self.identities.get_organization(self.repository.organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("entry_unavailable", "此志工入口目前無法使用", 403)
        return PublicOrganizationResult(
            id=organization.id,
            name=organization.name,
            applications_enabled=policy.applications_enabled,
            insurance_required=policy.insurance_required,
        )

    async def _status_for_user(
        self,
        user_id: UUID | None,
        organization: PublicOrganizationResult,
        *,
        now: datetime | None = None,
    ) -> VolunteerStatusResult:
        if user_id is None:
            status, next_actions = effective_application_status(None, None, now=now)
            if not organization.applications_enabled:
                next_actions = ["return_to_line"]
            return VolunteerStatusResult(organization, None, None, status, next_actions)
        history = await self.repository.applications_for_user(user_id)
        application = history[0] if history else None
        grant = None
        if application is not None and application.status == "approved":
            grant_getter = getattr(self.repository, "grant_for_application", None)
            if grant_getter is not None:
                grant = await grant_getter(application.id)
        status, next_actions = effective_application_status(application, grant, now=now)
        return VolunteerStatusResult(organization, application, grant, status, next_actions)

    async def status(
        self,
        *,
        id_token: str,
        entry_reference_id: UUID | None,
        verified_line_user_id: str | None = None,
        now: datetime | None = None,
    ) -> VolunteerStatusResult:
        if entry_reference_id is not None and not isinstance(entry_reference_id, UUID):
            raise DomainError("entry_unavailable", "此志工入口目前無法使用", 403)
        line_user_id = (
            verified_line_user_id
            if verified_line_user_id is not None
            else await self.verifier.verify(id_token)
        )
        organization = await self._public_organization()
        binding = await self.identities.get_line_binding(line_user_id)
        return await self._status_for_user(
            None if binding is None else binding.user_id, organization, now=now
        )

    async def submit(
        self,
        *,
        id_token: str,
        entry_reference_id: UUID | None,
        verified_line_user_id: str | None = None,
        client_request_id: UUID,
        consent_acknowledged: bool,
        organization_id: UUID | None = None,
        applicant_name: str | None = None,
        phone_number: str | None = None,
        basic_profile: dict[str, Any] | None = None,
        insurance_identity: str | None = None,
        insurance_consent_acknowledged: bool = False,
        service_dates: list[date] | None = None,
        now: datetime | None = None,
    ) -> VolunteerSubmitResult:
        if (entry_reference_id is None) == (organization_id is None):
            raise DomainError("volunteer_target_required", "志工申請目標無效", 422)
        if organization_id is not None and organization_id != self.repository.organization_id:
            raise DomainError("organization_scope_mismatch", "收容所資料範圍不符", 404)
        if not consent_acknowledged:
            raise DomainError("consent_required", "請先確認志工報名同意事項", 422)
        line_user_id = (
            verified_line_user_id
            if verified_line_user_id is not None
            else await self.verifier.verify(id_token)
        )
        organization = await self._public_organization()
        binding = await self.identities.get_line_binding(line_user_id)
        user_id = None if binding is None else binding.user_id
        if user_id is not None:
            existing = await self.repository.pending_application_for_user(user_id, for_update=True)
            if existing is not None:
                return VolunteerSubmitResult(
                    await self._status_for_user(user_id, organization, now=now), False
                )
        if not organization.applications_enabled:
            raise DomainError(
                "volunteer_applications_disabled",
                "此收容所目前暫停接受新申請",
                403,
            )
        if binding is None:
            identity_factory = getattr(self.identities, "get_or_create_line_applicant", None)
            if identity_factory is None:
                user = await self.identities.add(User(display_name="LINE 志工", status="active"))
                binding = await self.identities.add(
                    LineUserBinding(
                        line_user_id=line_user_id,
                        user_id=user.id,
                        status="active",
                    )
                )
            else:
                _, binding, _ = await identity_factory(line_user_id)
            user_id = binding.user_id
        assert user_id is not None
        history = await self.repository.applications_for_user(user_id)
        client_lookup = getattr(self.repository, "application_by_client_request", None)
        if client_lookup is not None:
            replay = await client_lookup(user_id, client_request_id)
            if replay is not None:
                return VolunteerSubmitResult(
                    await self._status_for_user(user_id, organization, now=now), False
                )
        if history and history[0].status == "approved":
            grant_getter = getattr(self.repository, "grant_for_application", None)
            grant = None if grant_getter is None else await grant_getter(history[0].id)
            if grant is None or grant.status == "active":
                raise DomainError(
                    "volunteer_access_cycle_active",
                    "目前已有核准或有效的志工授權",
                    409,
                )
        previous_application_id = history[0].id if history else None
        submitted_at = now or datetime.now(timezone.utc)
        normalized_service_dates = (
            validate_service_date_selection(service_dates, today=submitted_at.date())
            if service_dates is not None
            else []
        )
        policy = None
        normalized_identity = None
        if self.pii_service is not None:
            if not applicant_name or not phone_number:
                raise DomainError("application_profile_required", "請完整填寫志工資料", 422)
            policy = await self.repository.policy(for_update=True)
            normalized_identity = (insurance_identity or "").strip()
            if policy.insurance_required and not normalized_identity:
                raise DomainError("insurance_identity_required", "請提供保險身分資料", 422)
            if normalized_identity and not policy.insurance_required:
                raise DomainError("insurance_identity_not_allowed", "此申請不需保險身分資料", 422)
            if normalized_identity and not insurance_consent_acknowledged:
                raise DomainError("insurance_consent_required", "請先同意保險身分資料用途", 422)
        application = VolunteerApplication(
            organization_id=self.repository.organization_id,
            user_id=user_id,
            status="pending",
            source_channel="liff",
            client_request_id=client_request_id,
            previous_application_id=previous_application_id,
            submitted_at=submitted_at,
        )
        race_safe_add = getattr(self.repository, "add_application_with_race_recovery", None)
        if race_safe_add is None:
            application = await self.repository.add(application)
            created = True
        else:
            application, created = await race_safe_add(application)
        if created:
            if normalized_service_dates:
                add_service_dates = getattr(
                    self.repository, "add_service_dates_with_capacity", None
                )
                if add_service_dates is None:
                    raise DomainError("service_dates_unavailable", "服務日期暫時無法建立", 503)
                policy_for_dates = policy or await self.repository.policy()
                await add_service_dates(
                    application.id,
                    normalized_service_dates,
                    daily_limit=policy_for_dates.daily_application_limit,
                )
            if self.pii_service is not None:
                assert policy is not None
                await self.pii_service.create_profile(
                    repository=self.repository,
                    application_id=application.id,
                    applicant_name=applicant_name,
                    phone_number=phone_number,
                    basic_profile=basic_profile,
                    insurance_identity=normalized_identity or None,
                    insurance_consent_acknowledged=insurance_consent_acknowledged,
                    insurance_collection_mode=(
                        "strayhub_temporary" if normalized_identity else None
                    ),
                    insurance_purpose_code=(
                        "insurance_verification" if normalized_identity else None
                    ),
                    insurance_policy_version=(
                        f"organization-policy-v{policy.version}" if normalized_identity else None
                    ),
                    now=submitted_at,
                    request_id=client_request_id,
                )
            await self._record_submission(application, organization, binding.id)
        return VolunteerSubmitResult(
            await self._status_for_user(user_id, organization, now=submitted_at), created
        )

    async def withdraw(
        self,
        *,
        id_token: str,
        entry_reference_id: UUID,
        verified_line_user_id: str | None = None,
        application_id: UUID,
        expected_version: int,
        now: datetime | None = None,
    ) -> VolunteerStatusResult:
        line_user_id = (
            verified_line_user_id
            if verified_line_user_id is not None
            else await self.verifier.verify(id_token)
        )
        organization = await self._public_organization()
        binding = await self.identities.get_line_binding(line_user_id)
        if binding is None:
            raise DomainError("application_not_found", "找不到此志工申請", 404)
        application = await self.repository.application(application_id, for_update=True)
        if application is None or application.user_id != binding.user_id:
            raise DomainError("application_not_found", "找不到此志工申請", 404)
        if application.version != expected_version:
            raise DomainError("application_version_conflict", "申請狀態已更新，請重新載入", 409)
        before = {"status": application.status, "version": application.version}
        transition_application(application.status, "withdraw")
        application.status = "withdrawn"
        application.withdrawn_at = now or datetime.now(timezone.utc)
        application.version += 1
        if self.audit is not None:
            await self.audit.record(
                organization_id=self.repository.organization_id,
                actor_user_id=binding.user_id,
                action="volunteer_application.withdrawn",
                resource_type="volunteer_application",
                resource_id=application.id,
                source_channel="liff",
                before=before,
                after={"status": application.status, "version": application.version},
            )
        if self.notifications is not None:
            await self.notifications.enqueue(
                user_id=binding.user_id,
                line_binding_id=binding.id,
                event_type="application_withdrawn",
                resource_type="volunteer_application",
                resource_id=application.id,
                resource_version=application.version,
                payload={
                    "organization_name": organization.name,
                    "application_status": "withdrawn",
                },
            )
        return await self._status_for_user(binding.user_id, organization, now=now)

    async def _record_submission(
        self,
        application: VolunteerApplication,
        organization: PublicOrganizationResult,
        line_binding_id: UUID,
    ) -> None:
        if self.audit is not None:
            await self.audit.record(
                organization_id=self.repository.organization_id,
                actor_user_id=application.user_id,
                action="volunteer_application.submitted",
                resource_type="volunteer_application",
                resource_id=application.id,
                source_channel="liff",
                after={"status": "pending", "version": application.version},
            )
        if self.notifications is not None:
            await self.notifications.enqueue(
                user_id=application.user_id,
                line_binding_id=line_binding_id,
                event_type="application_submitted",
                resource_type="volunteer_application",
                resource_id=application.id,
                resource_version=application.version,
                payload={
                    "organization_name": organization.name,
                    "application_status": "pending",
                },
            )

    async def update_policy(
        self,
        *,
        actor_user_id: UUID,
        expected_version: int,
        applications_enabled: bool | None,
        default_grant_duration_hours: int | None,
        daily_application_limit: int | None = None,
    ) -> OrganizationVolunteerAccessPolicy:
        policy = await self.repository.policy(for_update=True)
        if policy.version != expected_version:
            raise DomainError("policy_version_conflict", "設定已更新，請重新載入", 409)
        if default_grant_duration_hours is not None and default_grant_duration_hours <= 0:
            raise DomainError("invalid_policy_duration", "預設授權期限必須大於 0", 422)
        if daily_application_limit is not None and daily_application_limit <= 0:
            raise DomainError("invalid_daily_application_limit", "每日申請上限必須大於 0", 422)
        before = {
            "applications_enabled": policy.applications_enabled,
            "default_grant_duration_hours": policy.default_grant_duration_hours,
            "daily_application_limit": policy.daily_application_limit,
            "version": policy.version,
        }
        if applications_enabled is not None:
            policy.applications_enabled = applications_enabled
        if default_grant_duration_hours is not None:
            policy.default_grant_duration_hours = default_grant_duration_hours
        if daily_application_limit is not None:
            policy.daily_application_limit = daily_application_limit
        policy.version += 1
        if self.audit is not None:
            await self.audit.record(
                organization_id=self.repository.organization_id,
                actor_user_id=actor_user_id,
                action="volunteer_access_policy.updated",
                resource_type="organization_volunteer_access_policy",
                resource_id=self.repository.organization_id,
                source_channel="api",
                before=before,
                after={
                    "applications_enabled": policy.applications_enabled,
                    "default_grant_duration_hours": policy.default_grant_duration_hours,
                    "daily_application_limit": policy.daily_application_limit,
                    "version": policy.version,
                },
            )
        return policy

    async def decide_application(
        self,
        *,
        application_id: UUID,
        expected_version: int,
        decision: str,
        actor_user_id: UUID,
        reason: str | None = None,
        valid_from: datetime | None = None,
        expires_at: datetime | None = None,
        policy_version_used: int | None = None,
        duration_hours_used: int | None = None,
        operation_id: UUID | None = None,
        service_date: date | None = None,
        now: datetime | None = None,
    ) -> tuple[VolunteerApplication, OrganizationMembership | None, VolunteerAccessGrant | None]:
        clock = now or datetime.now(timezone.utc)
        application = await self.repository.application(application_id, for_update=True)
        if application is None:
            raise DomainError("application_not_found", "找不到此志工申請", 404)
        if application.status != "pending" or application.version != expected_version:
            raise DomainError("application_version_conflict", "申請狀態已更新", 409)
        if decision not in {"approve", "reject"}:
            raise DomainError("invalid_batch_decision", "決策無效", 422)
        service_date_status = "approved" if decision == "approve" else "rejected"
        service_date_item = None
        if service_date is not None:
            getter = getattr(self.repository, "service_date_for_application", None)
            if getter is None:
                raise DomainError("service_date_unavailable", "服務日期暫時無法審核", 503)
            service_date_item = await getter(application.id, service_date, for_update=True)
            if service_date_item is None or service_date_item.status != "pending":
                raise DomainError("service_date_version_conflict", "服務日期已更新", 409)
            existing_grant = await self.repository.grant_for_application(application.id)
            if existing_grant is not None:
                service_date_item.status = service_date_status
                service_date_item.decided_at = clock
                service_date_item.decided_by_user_id = actor_user_id
                service_date_item.decision_reason = normalize_reason(
                    reason, required=decision == "reject"
                )
                service_date_item.version += 1
                pending_count = await self.repository.pending_service_date_count(application.id)
                application.status = "pending" if pending_count else "approved"
                application.decided_at = clock
                application.decided_by_user_id = actor_user_id
                application.version += 1
                membership = await self.identities.get_membership(
                    application.user_id, self.repository.organization_id
                )
                return application, membership, existing_grant
        before = {"status": application.status, "version": application.version}
        membership = None
        grant = None
        if decision == "reject":
            decision_reason = normalize_reason(reason, required=True)
            transition_application(application.status, "reject")
            application.status = "rejected"
            application.decision_reason = decision_reason
        elif decision == "approve":
            transition_application(application.status, "approve")
            policy = await self.repository.policy()
            policy_snapshot = snapshot_policy(
                version=policy_version_used or policy.version,
                duration_hours=duration_hours_used or policy.default_grant_duration_hours,
            )
            start = valid_from or clock
            end = expires_at or start + timedelta(hours=policy_snapshot["duration_hours_used"])
            start, end = validate_grant_period(start, end)
            membership = await self.identities.get_membership(
                application.user_id, self.repository.organization_id
            )
            if membership is not None and membership.role != "VOLUNTEER":
                raise DomainError("role_conflict", "既有管理角色不可轉為志工", 409)
            if membership is None:
                membership = await self.identities.add(
                    OrganizationMembership(
                        organization_id=self.repository.organization_id,
                        user_id=application.user_id,
                        role="VOLUNTEER",
                        status="active",
                        valid_from=start,
                        expires_at=end,
                        access_version=1,
                    )
                )
            else:
                membership.status = "active"
                membership.valid_from = start
                membership.expires_at = end
                membership.access_version += 1
            grant = await self.repository.add(
                VolunteerAccessGrant(
                    organization_id=self.repository.organization_id,
                    user_id=application.user_id,
                    membership_id=membership.id,
                    application_id=application.id,
                    status="active",
                    valid_from=start,
                    expires_at=end,
                    approved_at=clock,
                    approved_by_user_id=actor_user_id,
                    policy_version_used=policy_snapshot["policy_version_used"],
                    duration_hours_used=policy_snapshot["duration_hours_used"],
                    source_type="manager_approval",
                )
            )
            application.status = "approved"
            application.decision_reason = normalize_reason(reason)
        application.decided_at = clock
        application.decided_by_user_id = actor_user_id
        application.version += 1
        if service_date_item is not None:
            service_date_item.status = service_date_status
            service_date_item.decided_at = clock
            service_date_item.decided_by_user_id = actor_user_id
            service_date_item.decision_reason = normalize_reason(reason)
            service_date_item.version += 1
            if await self.repository.pending_service_date_count(application.id):
                application.status = "pending"
        if self.audit is not None:
            await self.audit.record(
                organization_id=self.repository.organization_id,
                actor_user_id=actor_user_id,
                action=f"volunteer_application.{application.status}",
                resource_type="volunteer_application",
                resource_id=application.id,
                operation_id=operation_id,
                source_channel="api",
                before=before,
                after={"status": application.status, "version": application.version},
                reason=application.decision_reason,
            )
        if self.notifications is not None:
            line_binding_getter = getattr(self.identities, "get_line_binding_for_user", None)
            line_binding = (
                None
                if line_binding_getter is None
                else await line_binding_getter(application.user_id)
            )
            await self.notifications.enqueue(
                user_id=application.user_id,
                line_binding_id=None if line_binding is None else line_binding.id,
                event_type="approved" if application.status == "approved" else "rejected",
                resource_type="volunteer_application",
                resource_id=application.id,
                resource_version=application.version,
                payload={
                    "organization_name": (await self._public_organization()).name,
                    "application_status": application.status,
                    "valid_from": None if grant is None else grant.valid_from,
                    "expires_at": None if grant is None else grant.expires_at,
                },
            )
        return application, membership, grant

    async def mutate_grant(
        self,
        *,
        grant_id: UUID,
        expected_version: int,
        action: str,
        actor_user_id: UUID,
        valid_from: datetime | None = None,
        expires_at: datetime | None = None,
        confirm_immediate_expiry: bool = False,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> VolunteerAccessGrant:
        clock = now or datetime.now(timezone.utc)
        grant = await self.repository.grant(grant_id, for_update=True)
        if grant is None:
            raise DomainError("grant_not_found", "找不到此志工授權", 404)
        if grant.version != expected_version:
            raise DomainError("grant_version_conflict", "授權已更新，請重新載入", 409)
        if grant.status != "active":
            raise DomainError("grant_terminal", "已結束的授權不可再修改", 409)
        membership = await self.identities.get_membership(
            grant.user_id, self.repository.organization_id
        )
        if membership is None or membership.id != grant.membership_id:
            raise DomainError("grant_projection_missing", "授權狀態不一致", 409)
        before = {
            "status": grant.status,
            "valid_from": grant.valid_from.isoformat(),
            "expires_at": grant.expires_at.isoformat(),
            "version": grant.version,
        }
        if action == "update_period":
            if valid_from is None or expires_at is None:
                raise DomainError("grant_period_required", "必須提供完整授權期間", 422)
            valid_from, expires_at = validate_grant_period(valid_from, expires_at)
            immediate = expires_at <= clock
            if immediate and not confirm_immediate_expiry:
                raise DomainError(
                    "immediate_expiry_confirmation_required",
                    "縮短期限將立即失效，請再次確認",
                    422,
                )
            grant.valid_from = valid_from
            grant.expires_at = expires_at
            membership.valid_from = valid_from
            membership.expires_at = expires_at
            if immediate:
                grant.status = "expired"
                membership.status = "disabled"
        elif action == "revoke":
            revocation_reason = normalize_reason(reason, required=True)
            grant.status = "revoked"
            grant.revoked_at = clock
            grant.revoked_by_user_id = actor_user_id
            grant.revocation_reason = revocation_reason
            membership.status = "disabled"
        else:
            raise DomainError("invalid_grant_action", "授權操作無效", 422)
        grant.version += 1
        membership.access_version += 1
        if grant.status in {"expired", "revoked"}:
            clear_contexts = getattr(self.identities, "clear_volunteer_contexts", None)
            if clear_contexts is not None:
                await clear_contexts(grant.user_id, self.repository.organization_id)
        if self.audit is not None:
            audit_transition = grant.status if grant.status != "active" else "period_updated"
            await self.audit.record(
                organization_id=self.repository.organization_id,
                actor_user_id=actor_user_id,
                action=f"volunteer_access_grant.{audit_transition}",
                resource_type="volunteer_access_grant",
                resource_id=grant.id,
                source_channel="api",
                before=before,
                after={
                    "status": grant.status,
                    "valid_from": grant.valid_from.isoformat(),
                    "expires_at": grant.expires_at.isoformat(),
                    "version": grant.version,
                },
                reason=grant.revocation_reason or normalize_reason(reason),
            )
        if self.notifications is not None:
            line_binding_getter = getattr(self.identities, "get_line_binding_for_user", None)
            line_binding = (
                None if line_binding_getter is None else await line_binding_getter(grant.user_id)
            )
            await self.notifications.enqueue(
                user_id=grant.user_id,
                line_binding_id=None if line_binding is None else line_binding.id,
                event_type={
                    "active": "grant_changed",
                    "expired": "expired",
                    "revoked": "revoked",
                }[grant.status],
                resource_type="volunteer_access_grant",
                resource_id=grant.id,
                resource_version=grant.version,
                payload={
                    "grant_status": grant.status,
                    "valid_from": grant.valid_from,
                    "expires_at": grant.expires_at,
                    "next_action": "reapply" if grant.status != "active" else "continue",
                },
            )
        return grant


__all__ = [
    "PublicOrganizationResult",
    "VolunteerAccessService",
    "VolunteerStatusResult",
    "VolunteerSubmitResult",
    "effective_application_status",
    "grant_remaining_seconds",
]
