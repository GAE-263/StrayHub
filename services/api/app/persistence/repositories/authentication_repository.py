from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.database.scope import (
    set_authentication_user_organization_scope,
    set_authentication_user_scope,
    set_organization_scope,
)
from services.api.app.persistence.database.scope import (
    set_platform_scope as set_database_platform_scope,
)
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    Organization,
    OrganizationMembership,
    RefreshTokenRecord,
    SessionRecord,
    User,
    WebhookSession,
)
from services.api.app.persistence.models.volunteer_access import (
    VolunteerAccessGrant,
    VolunteerApplication,
)

T = TypeVar("T")


class AuthenticationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def set_authentication_user_scope(self, user_id: UUID) -> None:
        await set_authentication_user_scope(self.session, user_id)

    async def set_authentication_context_scope(self, user_id: UUID, organization_id: UUID) -> None:
        await set_authentication_user_organization_scope(self.session, user_id, organization_id)

    async def set_platform_scope(self) -> None:
        await set_database_platform_scope(self.session)

    async def set_organization_scope(self, organization_id: UUID) -> None:
        await set_organization_scope(self.session, organization_id)

    async def effective_organization_access(
        self, user_id: UUID
    ) -> list[tuple[OrganizationMembership, Organization]]:
        """Discover own memberships, then verify each grant in exact auth scope.

        Authentication callers supply a verified user. Leaves auth-user scope;
        tenant request callers must restore their original organization scope.
        """
        await self.set_authentication_user_scope(user_id)
        candidates = await self.memberships(user_id)
        access = []
        try:
            for candidate in candidates:
                await self.set_authentication_context_scope(user_id, candidate.organization_id)
                membership = await self.get_effective_membership(user_id, candidate.organization_id)
                organization = await self.get_organization(candidate.organization_id)
                if (
                    membership is not None
                    and organization is not None
                    and organization.status == "active"
                ):
                    access.append((membership, organization))
            return access
        finally:
            await self.set_authentication_user_scope(user_id)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def lock_user(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def memberships(
        self, user_id: UUID, *, active_only: bool = False
    ) -> list[OrganizationMembership]:
        statement = select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
        if active_only:
            statement = statement.where(self._effective_membership_predicate())
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def access_grants_for_memberships(
        self, user_id: UUID, membership_ids: list[UUID]
    ) -> list[VolunteerAccessGrant]:
        if not membership_ids:
            return []
        result = await self.session.execute(
            select(VolunteerAccessGrant).where(
                VolunteerAccessGrant.user_id == user_id,
                VolunteerAccessGrant.membership_id.in_(membership_ids),
            )
        )
        return list(result.scalars())

    async def get_membership(
        self, user_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        statement = select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_effective_membership(
        self, user_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        result = await self.session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                self._effective_membership_predicate(),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_active_webhook_sessions(self, user_id: UUID) -> None:
        await self.session.execute(
            update(WebhookSession)
            .where(
                WebhookSession.user_id == user_id,
                WebhookSession.status == "active",
            )
            .values(status="revoked")
        )

    async def get_effective_volunteer_membership(
        self, user_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        result = await self.session.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "VOLUNTEER",
                self._effective_membership_predicate(),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def lock_effective_volunteer_access(
        self, user_id: UUID, organization_id: UUID
    ) -> tuple[OrganizationMembership, VolunteerAccessGrant] | None:
        """Lock the exact Membership and Grant used to authorize a LIFF session."""
        database_now = func.now()
        grant_result = await self.session.execute(
            select(VolunteerAccessGrant)
            .where(
                VolunteerAccessGrant.user_id == user_id,
                VolunteerAccessGrant.organization_id == organization_id,
                VolunteerAccessGrant.status == "active",
                VolunteerAccessGrant.valid_from <= database_now,
                VolunteerAccessGrant.expires_at > database_now,
            )
            .with_for_update()
        )
        grant = grant_result.scalar_one_or_none()
        if grant is None:
            return None
        membership_result = await self.session.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.id == grant.membership_id,
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "VOLUNTEER",
                OrganizationMembership.status == "active",
                OrganizationMembership.valid_from.is_not(None),
                OrganizationMembership.expires_at.is_not(None),
                OrganizationMembership.valid_from <= database_now,
                OrganizationMembership.expires_at > database_now,
            )
            .with_for_update()
        )
        membership = membership_result.scalar_one_or_none()
        return None if membership is None else (membership, grant)

    async def latest_volunteer_application(
        self, user_id: UUID, organization_id: UUID
    ) -> VolunteerApplication | None:
        result = await self.session.execute(
            select(VolunteerApplication)
            .where(
                VolunteerApplication.user_id == user_id,
                VolunteerApplication.organization_id == organization_id,
            )
            .order_by(
                VolunteerApplication.submitted_at.desc(),
                VolunteerApplication.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _effective_membership_predicate():
        database_now = func.now()
        return and_(
            OrganizationMembership.status == "active",
            or_(
                OrganizationMembership.role != "VOLUNTEER",
                and_(
                    OrganizationMembership.valid_from.is_not(None),
                    OrganizationMembership.expires_at.is_not(None),
                    OrganizationMembership.valid_from <= database_now,
                    OrganizationMembership.expires_at > database_now,
                    select(VolunteerAccessGrant.id)
                    .where(
                        VolunteerAccessGrant.membership_id == OrganizationMembership.id,
                        VolunteerAccessGrant.organization_id
                        == OrganizationMembership.organization_id,
                        VolunteerAccessGrant.status == "active",
                        VolunteerAccessGrant.valid_from <= database_now,
                        VolunteerAccessGrant.expires_at > database_now,
                    )
                    .exists(),
                ),
            ),
        )

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id)

    async def organizations(self, *, active_only: bool = False) -> list[Organization]:
        statement = select(Organization).order_by(Organization.name)
        if active_only:
            statement = statement.where(Organization.status == "active")
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def get_session(self, session_id: UUID) -> SessionRecord | None:
        return await self.session.get(SessionRecord, session_id)

    async def get_refresh_token(self, digest: str) -> RefreshTokenRecord | None:
        result = await self.session.execute(
            select(RefreshTokenRecord).where(RefreshTokenRecord.token_digest == digest)
        )
        return result.scalar_one_or_none()

    async def refresh_tokens_for_session(self, session_id: UUID) -> list[RefreshTokenRecord]:
        result = await self.session.execute(
            select(RefreshTokenRecord).where(RefreshTokenRecord.session_id == session_id)
        )
        return list(result.scalars())

    async def get_line_binding(self, line_user_id: str) -> LineUserBinding | None:
        result = await self.session.execute(
            select(LineUserBinding).where(
                LineUserBinding.line_user_id == line_user_id,
                LineUserBinding.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def lock_line_binding(self, line_user_id: str) -> LineUserBinding | None:
        result = await self.session.execute(
            select(LineUserBinding)
            .where(
                LineUserBinding.line_user_id == line_user_id,
                LineUserBinding.status == "active",
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_line_binding_for_user(self, user_id: UUID) -> LineUserBinding | None:
        result = await self.session.execute(
            select(LineUserBinding).where(
                LineUserBinding.user_id == user_id,
                LineUserBinding.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def clear_volunteer_contexts(self, user_id: UUID, organization_id: UUID) -> None:
        await self.session.execute(
            update(SessionRecord)
            .where(
                SessionRecord.user_id == user_id,
                SessionRecord.active_organization_id == organization_id,
            )
            .values(active_organization_id=None)
        )
        await self.session.execute(
            update(WebhookSession)
            .where(
                WebhookSession.user_id == user_id,
                WebhookSession.organization_id == organization_id,
                WebhookSession.status == "active",
            )
            .values(status="expired", expires_at=func.now())
        )

    async def get_or_create_line_applicant(
        self, line_user_id: str
    ) -> tuple[User, LineUserBinding, bool]:
        binding = await self.get_line_binding(line_user_id)
        if binding is not None:
            user = await self.get_user(binding.user_id)
            if user is None:
                raise RuntimeError("LINE binding references a missing user") from None
            return user, binding, False
        user = User(display_name="LINE 志工", status="active")
        binding = LineUserBinding(
            line_user_id=line_user_id,
            user_id=user.id,
            status="active",
        )
        try:
            async with self.session.begin_nested():
                self.session.add(user)
                await self.session.flush()
                binding.user_id = user.id
                self.session.add(binding)
                await self.session.flush()
            return user, binding, True
        except IntegrityError:
            binding = await self.get_line_binding(line_user_id)
            if binding is None:
                raise
            user = await self.get_user(binding.user_id)
            if user is None:
                raise RuntimeError("LINE binding references a missing user") from None
            return user, binding, False

    async def revoke_refresh_family(self, family_id: UUID) -> None:
        result = await self.session.execute(
            select(RefreshTokenRecord).where(RefreshTokenRecord.family_id == family_id)
        )
        for record in result.scalars():
            record.status = "revoked"

    async def add(self, value: T) -> T:
        self.session.add(value)
        await self.session.flush()
        return value
