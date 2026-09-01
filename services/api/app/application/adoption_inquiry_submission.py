from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.api.app.api.errors import DomainError
from services.api.app.domain.line_adoption_state import AdoptionInquiryAnswers
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.repositories.adoption_inquiry_repository import (
    AdoptionInquiryRepository,
)


class AdoptionInquirySubmissionService:
    def __init__(self, inquiries: AdoptionInquiryRepository, *, audit=None) -> None:
        self.inquiries = inquiries
        self.audit = audit

    async def submit(
        self,
        *,
        draft: AdoptionDraft,
        animal: Animal,
        answers: AdoptionInquiryAnswers,
        match_scores_snapshot: list[dict[str, Any]] | None = None,
    ) -> AdoptionInquiry:
        existing = await self.inquiries.get_by_draft(draft.id)
        if existing is not None:
            return existing
        if (
            draft.organization_id != self.inquiries.organization_id
            or animal.organization_id != draft.organization_id
        ):
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        if animal.status != "active" or not animal.is_adoptable:
            raise DomainError("animal_not_adoptable", "動物目前不可領養", 409)
        inquiry = await self.inquiries.add(
            AdoptionInquiry(
                organization_id=draft.organization_id,
                draft_id=draft.id,
                adopter_user_id=draft.adopter_user_id,
                path=answers.path.value,
                target_animal_id=animal.id,
                animal_name_snapshot=animal.name,
                shelter_number_snapshot=animal.shelter_number,
                answers=dict(answers.values),
                match_scores_snapshot=match_scores_snapshot,
                adopter_name=answers.values["adopter_name"],
                phone_number=answers.values["phone_number"],
                status="new",
                submitted_at=datetime.now(timezone.utc),
            )
        )
        if self.audit is not None:
            await self.audit.record(
                organization_id=inquiry.organization_id,
                actor_user_id=draft.adopter_user_id,
                action="adoption_inquiry.submitted",
                resource_type="adoption_inquiry",
                resource_id=inquiry.id,
                source_channel="line_bot",
                after={"animal_id": inquiry.target_animal_id, "draft_id": draft.id},
            )
        draft.status = "submitted"
        draft.current_step = "submitted"
        return inquiry
