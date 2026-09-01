from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry


class AdoptionInquiryRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, inquiry_id: UUID) -> AdoptionInquiry | None:
        result = await self.session.execute(
            select(AdoptionInquiry).where(
                AdoptionInquiry.id == inquiry_id,
                AdoptionInquiry.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_draft(self, draft_id: UUID) -> AdoptionInquiry | None:
        result = await self.session.execute(
            select(AdoptionInquiry).where(
                AdoptionInquiry.draft_id == draft_id,
                AdoptionInquiry.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, inquiry: AdoptionInquiry) -> AdoptionInquiry:
        if inquiry.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(inquiry)
        await self.session.flush()
        return inquiry


async def list_inquiries_for_adopter(
    session: AsyncSession, adopter_user_id: UUID
) -> list[AdoptionInquiry]:
    """Cross-organization by design: an adopter may have adopted through more
    than one shelter, and the growth-diary entry point needs to find every
    inquiry they've ever submitted regardless of which one."""
    result = await session.execute(
        select(AdoptionInquiry)
        .where(AdoptionInquiry.adopter_user_id == adopter_user_id)
        .order_by(AdoptionInquiry.submitted_at.desc())
    )
    return list(result.scalars())
