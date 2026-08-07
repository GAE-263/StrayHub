from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import issue_animal_confirmation_token
from services.api.app.application.create_report_draft import CreateReportDraftService
from services.api.app.persistence.models.care_report_draft import CareReportDraft


class _Repository:
    def __init__(self, organization_id):
        self.organization_id = organization_id
        self.drafts = []

    async def get_active_for_volunteer(self, volunteer_user_id):
        return next(
            (
                draft
                for draft in self.drafts
                if draft.volunteer_user_id == volunteer_user_id and draft.status == "active"
            ),
            None,
        )

    async def add(self, draft):
        self.drafts.append(draft)
        return draft


@pytest.mark.asyncio
async def test_draft_requires_server_issued_animal_confirmation() -> None:
    organization_id = uuid4()
    user_id = uuid4()
    membership_id = uuid4()
    session_id = uuid4()
    animal_id = uuid4()
    repository = _Repository(organization_id)
    service = CreateReportDraftService(repository, ttl_seconds=60)
    token = issue_animal_confirmation_token(
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        session_id=session_id,
        animal_id=animal_id,
    )

    draft, raw_token = await service.create(
        volunteer_user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        session_id=session_id,
        animal_id=animal_id,
        confirmation_token=token,
    )
    assert isinstance(draft, CareReportDraft)
    assert raw_token
    with pytest.raises(DomainError, match="確認回報的動物"):
        await service.create(
            volunteer_user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            session_id=session_id,
            animal_id=uuid4(),
            confirmation_token=token,
        )
