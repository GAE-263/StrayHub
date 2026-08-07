from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository


class Session:
    def add(self, _value):
        return None


@pytest.mark.asyncio
async def test_scoped_repositories_reject_cross_organization_writes() -> None:
    organization_a = uuid4()
    organization_b = uuid4()
    draft = type("Draft", (), {"organization_id": organization_b})()
    report = type("Report", (), {"organization_id": organization_b})()
    with pytest.raises(DomainError, match="其他收容所"):
        await CareReportDraftRepository(Session(), organization_a).add(draft)
    with pytest.raises(DomainError, match="其他收容所"):
        await CareReportRepository(Session(), organization_a).add(report)
