"""Invitation possession permits a claim, never shelter authorization."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, text

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.application.authentication.google_service import digest
from services.api.app.application.organization_management import OrganizationManagementService
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.database.scope import (
    set_authentication_user_scope,
    set_organization_scope,
)
from services.api.app.persistence.models.identity import (
    OrganizationInvitation,
    OrganizationJoinApplication,
    User,
)
from services.api.app.persistence.repositories.organization_repository import OrganizationRepository


class InvitationService:
    def __init__(self, session):
        self.db = session
        self.repository = OrganizationRepository(session)

    async def join_target(self, *, user_id: UUID, organization_id: UUID):
        await set_authentication_user_scope(self.db, user_id)
        row = (
            (
                await self.db.execute(
                    text("SELECT id, name FROM public.join_organization(:id)"),
                    {"id": organization_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError("join_target_unavailable", "此收容所無法接受申請", 404)
        return dict(row)

    @staticmethod
    def application_result(item, display_name=None):
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "organization_name": item.organization_name,
            "user_id": item.user_id,
            "status": item.status,
            "role": item.role,
            "created_at": item.created_at,
            "reviewed_at": item.reviewed_at,
            "display_name": display_name,
        }

    async def apply(self, *, user_id: UUID, organization_id: UUID):
        target = await self.join_target(user_id=user_id, organization_id=organization_id)
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"join:{organization_id}:{user_id}"},
        )
        if await self.repository.membership(user_id, organization_id) is not None:
            raise DomainError("membership_exists", "此帳號已有成員紀錄", 409)
        previous = (
            await self.db.scalars(
                select(OrganizationJoinApplication)
                .where(
                    OrganizationJoinApplication.organization_id == organization_id,
                    OrganizationJoinApplication.user_id == user_id,
                )
                .order_by(OrganizationJoinApplication.created_at.desc())
                .limit(1)
            )
        ).one_or_none()
        if previous and previous.status == "pending":
            return self.application_result(previous)
        if (
            previous
            and previous.status == "rejected"
            and previous.reviewed_at
            and (datetime.now(timezone.utc) - previous.reviewed_at < timedelta(days=1))
        ):
            raise DomainError("join_retry_later", "未通過後請隔一天再申請", 429)
        item = await self.repository.add(
            OrganizationJoinApplication(
                organization_id=organization_id,
                organization_name=target["name"],
                user_id=user_id,
                status="pending",
            )
        )
        await AuditService(self.db).record(
            organization_id=None,
            actor_user_id=user_id,
            resource_id=user_id,
            action="join_application.submitted",
            resource_type="account",
            source_channel="web",
            after={"application_id": item.id, "organization_id": organization_id},
        )
        return self.application_result(item)

    async def applications(self, *, user_id=None, context=None, organization_id=None):
        query = select(OrganizationJoinApplication, User.display_name).join(
            User, User.id == OrganizationJoinApplication.user_id
        )
        if organization_id is not None:
            await self._admin(context, organization_id)
            query = query.where(
                OrganizationJoinApplication.organization_id == organization_id,
                OrganizationJoinApplication.status == "pending",
            )
        else:
            await set_authentication_user_scope(self.db, user_id)
            query = query.where(OrganizationJoinApplication.user_id == user_id)
        rows = (
            await self.db.execute(
                query.order_by(OrganizationJoinApplication.created_at.desc()).limit(100)
            )
        ).all()
        return [self.application_result(item, name) for item, name in rows]

    async def review(self, *, context, organization_id, application_id, approve, role=None):
        if (approve and role not in {"STAFF", "SHELTER_ADMIN"}) or (not approve and role):
            raise DomainError("invalid_role", "請選擇有效角色", 422)
        await self._admin(context, organization_id)
        item = (
            await self.db.scalars(
                select(OrganizationJoinApplication)
                .where(
                    OrganizationJoinApplication.id == application_id,
                    OrganizationJoinApplication.organization_id == organization_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if item is None:
            raise DomainError("join_not_found", "找不到申請", 404)
        if item.status != "pending":
            raise DomainError("join_already_reviewed", "此申請已處理，請重新整理", 409)
        if approve:
            await self.db.execute(select(User).where(User.id == item.user_id).with_for_update())
            membership = await OrganizationManagementService(
                self.repository, Argon2PasswordHasher()
            ).create_membership(organization_id=organization_id, user_id=item.user_id, role=role)
            await AuditService(self.db).record(
                organization_id=organization_id,
                actor_user_id=context.user_id,
                resource_type="organization_membership",
                resource_id=membership.id,
                action="membership.created",
                source_channel="web",
                after={"user_id": item.user_id, "role": role},
            )
        item.status = "approved" if approve else "rejected"
        item.role = role if approve else None
        item.reviewed_by = context.user_id
        item.reviewed_at = datetime.now(timezone.utc)
        await AuditService(self.db).record(
            organization_id=organization_id,
            actor_user_id=context.user_id,
            resource_type="organization_join_application",
            resource_id=item.id,
            action="join_application." + item.status,
            source_channel="web",
            after={"user_id": item.user_id, "role": item.role, "status": item.status},
        )
        return self.application_result(item)

    async def _admin(self, context, organization_id: UUID):
        OrganizationManagementService.require_settings_admin(
            role=context.role,
            platform_scope=context.platform_scope,
            current_organization_id=context.organization_id,
            target_organization_id=organization_id,
        )
        await set_organization_scope(self.db, organization_id)
        organization = await self.repository.lock_organization(organization_id)
        if organization is None or organization.status != "active":
            raise DomainError("organization_not_active", "收容所無法使用", 409)
        # Recheck after taking the same tenant lock used by existing mutations.
        actor = (
            await self.db.scalars(
                select(User)
                .where(User.id == context.user_id)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        membership = await self.repository.membership(context.user_id, organization_id)
        if (
            actor is None
            or actor.status != "active"
            or not (
                actor.platform_role == "PLATFORM_ADMIN"
                or (
                    membership
                    and membership.status == "active"
                    and membership.role == "SHELTER_ADMIN"
                )
            )
        ):
            raise DomainError("membership_management_denied", "無法管理此收容所", 403)
        return organization

    async def _audit(self, invitation, actor, action):
        await AuditService(self.db).record(
            organization_id=invitation.organization_id,
            actor_user_id=actor,
            resource_type="organization_invitation",
            resource_id=invitation.id,
            action=action,
            source_channel="web",
            after={"status": invitation.status, "role": invitation.role},
        )

    @staticmethod
    def serialize(invitation, display_name=None):
        expired = invitation.expires_at <= datetime.now(timezone.utc)
        return {
            "id": invitation.id,
            "organization_id": invitation.organization_id,
            "organization_name": invitation.organization_name,
            "role": invitation.role,
            "status": "expired"
            if expired and invitation.status in {"open", "claimed"}
            else invitation.status,
            "expires_at": invitation.expires_at,
            "claimed_by": invitation.claimed_by,
            "display_name": display_name,
        }

    async def create(self, *, context, organization_id: UUID, role: str) -> dict:
        organization = await self._admin(context, organization_id)
        if role not in {"STAFF", "SHELTER_ADMIN"}:
            raise DomainError("invalid_role", "邀請角色無效", 422)
        token = secrets.token_urlsafe(32)
        invitation = await self.repository.add(
            OrganizationInvitation(
                organization_id=organization.id,
                organization_name=organization.name,
                token_digest=digest(token),
                role=role,
                status="open",
                created_by=context.user_id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=3),
            )
        )
        await self._audit(invitation, context.user_id, "invitation.created")
        return {**self.serialize(invitation), "invitation_token": token}

    async def list(self, *, user_id=None, context=None, organization_id=None) -> list[dict]:
        if organization_id is not None:
            await self._admin(context, organization_id)
            rows = (
                await self.db.execute(
                    select(OrganizationInvitation, User.display_name)
                    .outerjoin(User, User.id == OrganizationInvitation.claimed_by)
                    .where(OrganizationInvitation.organization_id == organization_id)
                    .order_by(OrganizationInvitation.created_at.desc())
                    .limit(100)
                )
            ).all()
            return [self.serialize(invitation, name) for invitation, name in rows]
        await set_authentication_user_scope(self.db, user_id)
        rows = (
            await self.db.scalars(
                select(OrganizationInvitation)
                .where(OrganizationInvitation.claimed_by == user_id)
                .order_by(OrganizationInvitation.created_at.desc())
                .limit(100)
            )
        ).all()
        return [self.serialize(row) for row in rows]

    async def claim(self, *, user_id: UUID, token: str) -> dict:
        await set_authentication_user_scope(self.db, user_id)
        await self.db.execute(
            text("SELECT set_config('app.invitation_digest', :digest, true)"),
            {"digest": digest(token)},
        )
        invitation = (
            await self.db.scalars(
                select(OrganizationInvitation)
                .where(OrganizationInvitation.token_digest == digest(token))
                .with_for_update()
            )
        ).one_or_none()
        if (
            invitation is None
            or invitation.status not in {"open", "claimed"}
            or invitation.expires_at <= datetime.now(timezone.utc)
            or invitation.claimed_by not in {None, user_id}
        ):
            raise DomainError("invitation_invalid", "邀請碼無效或已到期", 404)
        invitation.claimed_by = user_id
        invitation.status = "claimed"
        await self.db.flush()
        await self.db.execute(text("SELECT set_config('app.invitation_digest', '', true)"))
        await AuditService(self.db).record(
            organization_id=None,
            actor_user_id=user_id,
            resource_id=user_id,
            action="invitation.claimed",
            resource_type="account",
            source_channel="web",
        )
        return self.serialize(invitation)

    async def decide(self, *, context, organization_id: UUID, invitation_id: UUID, approve: bool):
        await self._admin(context, organization_id)
        invitation = (
            await self.db.scalars(
                select(OrganizationInvitation)
                .where(
                    OrganizationInvitation.id == invitation_id,
                    OrganizationInvitation.organization_id == organization_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        if invitation is None:
            raise DomainError("invitation_not_found", "找不到邀請", 404)
        if invitation.status not in {"open", "claimed"}:
            raise DomainError("invitation_closed", "邀請已結束", 409)
        if approve:
            if invitation.status != "claimed" or invitation.expires_at <= datetime.now(
                timezone.utc
            ):
                raise DomainError("invitation_not_claimed", "邀請尚未認領或已到期", 409)
            # User lock serializes account status changes where supported.
            await self.db.execute(
                select(User).where(User.id == invitation.claimed_by).with_for_update()
            )
            membership = await OrganizationManagementService(
                self.repository, Argon2PasswordHasher()
            ).create_membership(
                organization_id=organization_id, user_id=invitation.claimed_by, role=invitation.role
            )
            invitation.status = "approved"
            await AuditService(self.db).record(
                organization_id=organization_id,
                actor_user_id=context.user_id,
                action="membership.created",
                resource_type="organization_membership",
                resource_id=membership.id,
                source_channel="web",
                after={"user_id": membership.user_id, "role": membership.role},
            )
        else:
            invitation.status = "revoked"
        await self._audit(invitation, context.user_id, "invitation." + invitation.status)
        return self.serialize(invitation)
