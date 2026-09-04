"""Allowlisted cross-organization projection for volunteer visit statistics."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.domain.volunteer_experience import VolunteerVisitRecord
from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.models.volunteer_management import VolunteerRestriction


class VolunteerServiceSummaryRepository:
    """Returns only inputs needed for aggregates; callers never expose rows."""

    def __init__(self, session: AsyncSession, current_organization_id: UUID) -> None:
        self.session = session
        self.current_organization_id = current_organization_id

    async def list_visit_records(self, subject_user_id: UUID) -> list[VolunteerVisitRecord]:
        service_date = cast(
            func.timezone(Organization.timezone, CareReport.submitted_at), Date
        ).label("service_date")
        statement = (
            select(CareReport.organization_id, service_date, func.max(CareReport.submitted_at))
            .join(Organization, Organization.id == CareReport.organization_id)
            .where(CareReport.volunteer_user_id == subject_user_id)
            .group_by(CareReport.organization_id, service_date)
        )
        await set_platform_scope(self.session)
        try:
            rows = (await self.session.execute(statement)).all()
        finally:
            await set_organization_scope(self.session, self.current_organization_id)
        return [
            VolunteerVisitRecord(
                organization_id=organization_id,
                service_date=service_date_value,
                last_activity_at=last_activity_at,
            )
            for organization_id, service_date_value, last_activity_at in rows
        ]

    async def has_active_platform_restriction(self, subject_user_id: UUID) -> bool:
        statement = select(VolunteerRestriction.id).where(
            VolunteerRestriction.volunteer_user_id == subject_user_id,
            VolunteerRestriction.scope == "PLATFORM",
            VolunteerRestriction.status == "active",
            VolunteerRestriction.starts_at <= func.now(),
            VolunteerRestriction.ends_at.is_(None) | (VolunteerRestriction.ends_at > func.now()),
        )
        await set_platform_scope(self.session)
        try:
            return (await self.session.execute(statement.limit(1))).scalar_one_or_none() is not None
        finally:
            await set_organization_scope(self.session, self.current_organization_id)
