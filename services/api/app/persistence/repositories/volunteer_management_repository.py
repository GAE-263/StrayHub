from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User
from services.api.app.persistence.models.volunteer_management import (
    VolunteerIncident,
    VolunteerNote,
    VolunteerProfile,
    VolunteerRestriction,
)


class VolunteerManagementRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def volunteer_membership(
        self, membership_id: UUID, *, for_update: bool = False
    ) -> OrganizationMembership | None:
        statement = select(OrganizationMembership).where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == self.organization_id,
            OrganizationMembership.role == "VOLUNTEER",
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def profile(self, user_id: UUID) -> VolunteerProfile | None:
        return await self.session.get(VolunteerProfile, user_id)

    async def notes(self, membership_id: UUID) -> list[tuple[VolunteerNote, str]]:
        result = await self.session.execute(
            select(VolunteerNote, User.display_name)
            .join(
                OrganizationMembership,
                OrganizationMembership.id == VolunteerNote.author_membership_id,
            )
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                VolunteerNote.organization_id == self.organization_id,
                VolunteerNote.subject_membership_id == membership_id,
            )
            .order_by(VolunteerNote.created_at.desc(), VolunteerNote.id.desc())
        )
        return list(result.all())

    async def add_note(self, note: VolunteerNote) -> VolunteerNote:
        self.session.add(note)
        await self.session.flush()
        return note

    async def incidents(self, membership_id: UUID) -> list[VolunteerIncident]:
        result = await self.session.execute(
            select(VolunteerIncident)
            .where(
                VolunteerIncident.organization_id == self.organization_id,
                VolunteerIncident.subject_membership_id == membership_id,
            )
            .order_by(VolunteerIncident.occurred_at.desc(), VolunteerIncident.id.desc())
        )
        return list(result.scalars())

    async def incident(
        self, incident_id: UUID, *, for_update: bool = False
    ) -> VolunteerIncident | None:
        statement = select(VolunteerIncident).where(
            VolunteerIncident.id == incident_id,
            VolunteerIncident.organization_id == self.organization_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def add_incident(self, incident: VolunteerIncident) -> VolunteerIncident:
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def add_restriction(self, restriction: VolunteerRestriction) -> VolunteerRestriction:
        self.session.add(restriction)
        await self.session.flush()
        return restriction

    async def restrictions(self, membership: OrganizationMembership) -> list[VolunteerRestriction]:
        result = await self.session.execute(
            select(VolunteerRestriction)
            .where(
                VolunteerRestriction.organization_id == self.organization_id,
                VolunteerRestriction.volunteer_user_id == membership.user_id,
            )
            .order_by(VolunteerRestriction.created_at.desc(), VolunteerRestriction.id.desc())
        )
        return list(result.scalars())

    async def platform_restriction_for_update(
        self, restriction_id: UUID
    ) -> VolunteerRestriction | None:
        result = await self.session.execute(
            select(VolunteerRestriction)
            .where(
                VolunteerRestriction.id == restriction_id,
                VolunteerRestriction.scope == "PLATFORM",
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def pending_platform_restrictions(
        self,
    ) -> list[tuple[VolunteerRestriction, VolunteerIncident, str]]:
        result = await self.session.execute(
            select(VolunteerRestriction, VolunteerIncident, Organization.name)
            .join(VolunteerIncident, VolunteerIncident.id == VolunteerRestriction.incident_id)
            .join(Organization, Organization.id == VolunteerRestriction.organization_id)
            .where(
                VolunteerRestriction.scope == "PLATFORM",
                VolunteerRestriction.status == "pending_review",
            )
            .order_by(VolunteerRestriction.created_at, VolunteerRestriction.id)
        )
        return list(result.all())

    async def flush(self) -> None:
        await self.session.flush()
