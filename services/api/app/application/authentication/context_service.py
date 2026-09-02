from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.models.identity import SessionRecord, WebhookSession
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)


class ActiveShelterContextService:
    def __init__(
        self, repository: AuthenticationRepository, *, audit: AuditService | None = None
    ) -> None:
        self.repository = repository
        self.audit = audit

    async def get(self, *, session_id: UUID) -> SessionRecord:
        session = await self.repository.get_session(session_id)
        if (
            session is None
            or session.status != "active"
            or session.expires_at <= datetime.now(timezone.utc)
        ):
            raise DomainError("invalid_session", "Session 無效", 401)
        return session

    async def switch(self, *, session_id: UUID, organization_id: UUID) -> SessionRecord:
        session = await self.get(session_id=session_id)
        user = await self.repository.get_user(session.user_id)
        if user is None or user.status != "active":
            raise DomainError("invalid_session", "使用者無效", 401)
        if user.platform_role != "PLATFORM_ADMIN":
            # The incoming request is scoped to A. Inspect only this authenticated
            # user's access to B before enabling any B tenant read/write capability.
            await self.repository.set_authentication_context_scope(user.id, organization_id)
        organization = await self.repository.get_organization(organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("organization_access_denied", "無法存取此收容所資料", 404)
        if user.platform_role != "PLATFORM_ADMIN":
            effective_getter = getattr(self.repository, "get_effective_membership", None)
            if effective_getter is None:
                membership = await self.repository.get_membership(user.id, organization_id)
            else:
                membership = await effective_getter(user.id, organization_id)
            if membership is None or organization is None or organization.status != "active":
                raise DomainError("organization_access_denied", "無法存取此收容所資料", 404)
        previous_organization_id = session.active_organization_id
        line_binding = await self.repository.get_line_binding_for_user(user.id)
        rotate_webhook_context = (
            line_binding is not None and previous_organization_id != organization_id
        )
        if rotate_webhook_context:
            locked_binding = await self.repository.lock_line_binding(line_binding.line_user_id)
            if locked_binding is None or locked_binding.user_id != user.id:
                raise DomainError("line_binding_invalid", "LINE 身分綁定無效", 403)

            # A line-bound user has one trusted webhook context. Revoke every
            # session visible through that user's current active memberships,
            # including an old context during initial None -> B selection.
            await self.repository.set_authentication_user_scope(user.id)
            # Auth-user RLS already exposes only this user's active membership
            # rows. Do not apply the effective volunteer predicate here: its
            # grant subquery is tenant-scoped and would hide every membership
            # while no exact organization scope is selected.
            memberships = await self.repository.memberships(user.id)
            webhook_organizations = {item.organization_id for item in memberships}
            webhook_organizations.add(organization_id)
            if previous_organization_id is not None:
                webhook_organizations.add(previous_organization_id)
            for webhook_organization_id in webhook_organizations:
                await self.repository.set_organization_scope(webhook_organization_id)
                await self.repository.revoke_active_webhook_sessions(user.id)
        # Scope, session and audit belong to the caller's single transaction.
        # Never flush the target audit under the old organization scope.
        await self.repository.set_organization_scope(organization_id)
        session.active_organization_id = organization_id
        if rotate_webhook_context:
            await self.repository.add(
                WebhookSession(
                    user_id=user.id,
                    organization_id=organization_id,
                    status="active",
                    expires_at=session.expires_at,
                )
            )
        if self.audit is not None:
            await self.audit.record(
                organization_id=organization_id,
                actor_user_id=user.id,
                action="shelter_context.switched",
                resource_type="SessionRecord",
                resource_id=session.id,
                source_channel="api",
                before={"organization_id": previous_organization_id},
                after={"organization_id": organization_id},
            )
        return session
