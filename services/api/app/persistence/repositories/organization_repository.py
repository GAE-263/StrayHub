from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
)


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, organization_id: UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id)

    async def list(self) -> list[Organization]:
        result = await self.session.execute(select(Organization).order_by(Organization.name))
        return list(result.scalars())

    async def add(self, value: object) -> object:
        self.session.add(value)
        await self.session.flush()
        return value

    async def create_with_volunteer_policy(self, *, code: str, name: str) -> Organization:
        async with self.session.begin_nested():
            organization = Organization(code=code, name=name, status="pending_setup")
            self.session.add(organization)
            await self.session.flush()
            self.session.add(
                OrganizationVolunteerAccessPolicy(
                    organization_id=organization.id,
                    applications_enabled=True,
                    default_grant_duration_hours=168,
                )
            )
            await self.session.flush()
        return organization

    async def membership(
        self, user_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        result = await self.session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def memberships(self, organization_id: UUID) -> list[OrganizationMembership]:
        result = await self.session.execute(
            select(OrganizationMembership)
            .where(OrganizationMembership.organization_id == organization_id)
            .order_by(OrganizationMembership.created_at)
        )
        return list(result.scalars())

    async def membership_by_id(
        self, membership_id: UUID, organization_id: UUID
    ) -> OrganizationMembership | None:
        result = await self.session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.id == membership_id,
                OrganizationMembership.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()
