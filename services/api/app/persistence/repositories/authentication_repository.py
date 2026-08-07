from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.identity import (
    LineUserBinding,
    Organization,
    OrganizationMembership,
    RefreshTokenRecord,
    SessionRecord,
    User,
)


class AuthenticationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def memberships(
        self, user_id: UUID, *, active_only: bool = False
    ) -> list[OrganizationMembership]:
        statement = select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
        if active_only:
            statement = statement.where(OrganizationMembership.status == "active")
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def get_membership(
        self, user_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        result = await self.session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id)

    async def get_session(self, session_id: UUID) -> SessionRecord | None:
        return await self.session.get(SessionRecord, session_id)

    async def get_refresh_token(self, digest: str) -> RefreshTokenRecord | None:
        result = await self.session.execute(
            select(RefreshTokenRecord).where(RefreshTokenRecord.token_digest == digest)
        )
        return result.scalar_one_or_none()

    async def get_line_binding(self, line_user_id: str) -> LineUserBinding | None:
        result = await self.session.execute(
            select(LineUserBinding).where(
                LineUserBinding.line_user_id == line_user_id,
                LineUserBinding.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_family(self, family_id: UUID) -> None:
        result = await self.session.execute(
            select(RefreshTokenRecord).where(RefreshTokenRecord.family_id == family_id)
        )
        for record in result.scalars():
            record.status = "revoked"

    async def add(self, value: object) -> object:
        self.session.add(value)
        await self.session.flush()
        return value
