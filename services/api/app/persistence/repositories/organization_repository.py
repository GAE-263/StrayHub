from __future__ import annotations

import builtins
from typing import TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.database.scope import set_public_volunteer_directory_scope
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
    VolunteerAccessGrant,
)

T = TypeVar("T")


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, organization_id: UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id)

    async def lock_organization(self, organization_id: UUID) -> Organization | None:
        """Lock the tenant row while a membership mutation is validated and saved."""

        result = await self.session.execute(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list(self) -> list[Organization]:
        result = await self.session.execute(select(Organization).order_by(Organization.name))
        return list(result.scalars())

    async def list_public_volunteer_organizations(
        self,
    ) -> list[tuple[UUID, str, str | None, str | None]]:
        statement = (
            select(
                Organization.id,
                Organization.name,
                Organization.address,
                Organization.service_area,
            )
            .join(
                OrganizationVolunteerAccessPolicy,
                OrganizationVolunteerAccessPolicy.organization_id == Organization.id,
            )
            .where(
                Organization.status == "active",
                OrganizationVolunteerAccessPolicy.applications_enabled.is_(True),
            )
            .order_by(Organization.service_area, Organization.name, Organization.id)
        )
        await set_public_volunteer_directory_scope(self.session)
        result = await self.session.execute(statement)
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def add(self, value: T) -> T:
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

    async def memberships(self, organization_id: UUID) -> builtins.list[OrganizationMembership]:
        result = await self.session.execute(
            select(OrganizationMembership)
            .where(OrganizationMembership.organization_id == organization_id)
            .order_by(OrganizationMembership.created_at)
        )
        return list(result.scalars())

    async def memberships_with_users(
        self, organization_id: UUID, *, include_archived: bool = False
    ) -> builtins.list[tuple[OrganizationMembership, User]]:
        statement = (
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(OrganizationMembership.organization_id == organization_id)
            .order_by(OrganizationMembership.created_at)
        )
        if not include_archived:
            statement = statement.where(OrganizationMembership.status != "archived")
        result = await self.session.execute(statement)
        return list(result.all())

    async def count_active_shelter_admins(
        self, organization_id: UUID, *, exclude_membership_id: UUID | None = None
    ) -> int:
        statement = select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.role == "SHELTER_ADMIN",
            OrganizationMembership.status == "active",
        )
        if exclude_membership_id is not None:
            statement = statement.where(OrganizationMembership.id != exclude_membership_id)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def volunteer_authorization_statuses(
        self, organization_id: UUID, membership_ids: builtins.list[UUID]
    ) -> dict[UUID, str]:
        if not membership_ids:
            return {}
        result = await self.session.execute(
            select(VolunteerAccessGrant.membership_id, VolunteerAccessGrant.status)
            .where(
                VolunteerAccessGrant.organization_id == organization_id,
                VolunteerAccessGrant.membership_id.in_(membership_ids),
            )
            .order_by(VolunteerAccessGrant.approved_at.desc(), VolunteerAccessGrant.id.desc())
        )
        statuses: dict[UUID, str] = {}
        for membership_id, grant_status in result.all():
            statuses.setdefault(membership_id, grant_status)
        return statuses

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
