from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
from services.api.app.persistence.models.animal import Animal

_ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "new": {"contacted", "closed"},
    "contacted": {"in_review", "closed"},
    "in_review": {"contacted", "closed"},
    "closed": set(),
}


class AdoptionInboxService:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @staticmethod
    def payload(inquiry: AdoptionInquiry, *, animal: Animal | None = None) -> dict:
        return {
            "id": str(inquiry.id),
            "organization_id": str(inquiry.organization_id),
            "path": inquiry.path,
            "target_animal_id": str(inquiry.target_animal_id),
            "animal_name": animal.name if animal else inquiry.animal_name_snapshot,
            "animal_name_snapshot": inquiry.animal_name_snapshot,
            "shelter_number_snapshot": inquiry.shelter_number_snapshot,
            "answers": inquiry.answers,
            "match_scores_snapshot": inquiry.match_scores_snapshot,
            "adopter_name": inquiry.adopter_name,
            "phone_number": inquiry.phone_number,
            "status": inquiry.status,
            "submitted_at": inquiry.submitted_at.isoformat(),
            "staff_notes": inquiry.staff_notes,
            "status_updated_at": (
                inquiry.status_updated_at.isoformat() if inquiry.status_updated_at else None
            ),
        }

    async def list(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        animal_id: UUID | None,
        inquiry_status: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        filters = [AdoptionInquiry.organization_id == self.organization_id]
        if from_date:
            filters.append(
                AdoptionInquiry.submitted_at
                >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
            )
        if to_date:
            filters.append(
                AdoptionInquiry.submitted_at
                <= datetime.combine(to_date, time.max, tzinfo=timezone.utc)
            )
        if animal_id:
            filters.append(AdoptionInquiry.target_animal_id == animal_id)
        if inquiry_status:
            filters.append(AdoptionInquiry.status == inquiry_status)
        total = await self.session.scalar(select(func.count(AdoptionInquiry.id)).where(*filters))
        rows = await self.session.execute(
            select(AdoptionInquiry, Animal)
            .outerjoin(
                Animal,
                and_(
                    Animal.id == AdoptionInquiry.target_animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .where(*filters)
            .order_by(AdoptionInquiry.submitted_at.desc(), AdoptionInquiry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [self.payload(inquiry, animal=animal) for inquiry, animal in rows.all()],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }

    async def detail(self, inquiry_id: UUID) -> dict:
        row = await self.session.execute(
            select(AdoptionInquiry, Animal)
            .outerjoin(
                Animal,
                and_(
                    Animal.id == AdoptionInquiry.target_animal_id,
                    Animal.organization_id == self.organization_id,
                ),
            )
            .where(
                AdoptionInquiry.id == inquiry_id,
                AdoptionInquiry.organization_id == self.organization_id,
            )
        )
        pair = row.one_or_none()
        if pair is None:
            raise DomainError("adoption_inquiry_not_found", "領養意願不存在或無法存取", 404)
        inquiry, animal = pair
        return self.payload(inquiry, animal=animal)

    async def update_status(
        self, inquiry_id: UUID, *, status: str, staff_notes: str | None, actor_user_id: UUID
    ) -> dict:
        inquiry = (
            await self.session.execute(
                select(AdoptionInquiry)
                .where(
                    AdoptionInquiry.id == inquiry_id,
                    AdoptionInquiry.organization_id == self.organization_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if inquiry is None:
            raise DomainError("adoption_inquiry_not_found", "領養意願不存在或無法存取", 404)
        allowed = _ALLOWED_STATUS_TRANSITIONS.get(inquiry.status, set())
        if status != inquiry.status and status not in allowed:
            raise DomainError("invalid_status_transition", "不允許的領養意願狀態轉移", 409)
        before_status = inquiry.status
        inquiry.status = status
        inquiry.staff_notes = staff_notes
        inquiry.status_updated_at = datetime.now(timezone.utc)
        inquiry.status_updated_by_user_id = actor_user_id
        await AuditService(self.session).record(
            organization_id=self.organization_id,
            actor_user_id=actor_user_id,
            action="adoption_inquiry.status_changed",
            resource_type="AdoptionInquiry",
            resource_id=inquiry.id,
            source_channel="api",
            before={"status": before_status},
            after={"status": status, "staff_notes": staff_notes},
        )
        await self.session.commit()
        return self.payload(inquiry)
