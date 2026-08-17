from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.database.scope import set_authentication_user_scope
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    Organization,
    OrganizationMembership,
    RefreshTokenRecord,
    SessionRecord,
    User,
    WebhookSession,
)
from services.api.app.persistence.models.volunteer_access import VolunteerAccessGrant

T = TypeVar("T")


class AuthenticationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def set_authentication_user_scope(self, user_id: UUID) -> None:
        await set_authentication_user_scope(self.session, user_id)

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def memberships(
        self, user_id: UUID, *, active_only: bool = False
    ) -> list[OrganizationMembership]:
        statement = select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
        if active_only:
            statement = statement.where(self._effective_membership_predicate())
        result = await self.session.execute(statement)
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
