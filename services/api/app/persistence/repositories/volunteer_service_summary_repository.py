"""Narrow cross-organization read model for volunteer service evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import Date, Select, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from services.api.app.persistence.models.care_report import CareReport
from services.api.app.persistence.models.identity import Organization


@dataclass(frozen=True)
class VolunteerServiceSummaryRecord:
    organization_id: UUID
    organization_name: str
    service_date: date
    service_status: str
    record_count: int
    source: str = "care_report"


class VolunteerServiceSummaryRepository:
    """Dedicated allowlisted cross-organization service-history read boundary."""

    def __init__(self, session: AsyncSession, current_organization_id: UUID) -> None:
        self.session = session
        self.current_organization_id = current_organization_id

    async def list_for_subject(
        self,
        subject_user_id: UUID,
        *,
        cursor: tuple[date, UUID] | None = None,
        limit: int = 50,
    ) -> list[VolunteerServiceSummaryRecord]:
        service_date = cast(CareReport.submitted_at, Date).label("service_date")
        service_status = case(
            (CareReport.status == "archived", "archived"),
            else_="recorded",
        ).label("service_status")
        statement: Select = (
            select(
                Organization.id,
                Organization.name,
                service_date,
                service_status,
                func.count(CareReport.id),
            )
            .join(Organization, Organization.id == CareReport.organization_id)
            .where(
                CareReport.volunteer_user_id == subject_user_id,
                CareReport.submitted_at.is_not(None),
            )
            .group_by(Organization.id, Organization.name, service_date, service_status)
        )
        if cursor is not None:
            cursor_date, cursor_organization_id = cursor
            statement = statement.where(
                or_(
                    service_date < cursor_date,
                    and_(
                        service_date == cursor_date,
                        Organization.id > cursor_organization_id,
                    ),
                )
            )
        statement = statement.order_by(service_date.desc(), Organization.id).limit(
            min(max(limit, 1), 100)
        )

        await set_platform_scope(self.session)
        try:
            result = await self.session.execute(statement)
            rows = result.all()
        finally:
            await set_organization_scope(self.session, self.current_organization_id)

        return [
            VolunteerServiceSummaryRecord(
                organization_id=organization_id,
                organization_name=organization_name,
                service_date=service_date_value,
                service_status=service_status_value,
                record_count=int(record_count),
            )
            for (
                organization_id,
                organization_name,
                service_date_value,
                service_status_value,
                record_count,
            ) in rows
        ]
