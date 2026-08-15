from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_access_service import (
    VolunteerAccessService,
    effective_application_status,
)
from services.api.app.domain.volunteer_access import ENTRY_REFERENCE_PURPOSE

NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)


def test_effective_status_and_next_actions_cover_onboarding_states() -> None:
    assert effective_application_status(None, None, now=NOW) == ("none", ["apply"])
    assert effective_application_status(SimpleNamespace(status="pending"), None, now=NOW) == (
        "pending",
        ["wait", "withdraw"],
    )
    assert effective_application_status(SimpleNamespace(status="rejected"), None, now=NOW) == (
        "rejected",
        ["reapply", "contact_shelter"],
    )
    grant = SimpleNamespace(
        status="active",
        valid_from=NOW + timedelta(hours=1),
        expires_at=NOW + timedelta(days=7),
    )
    assert effective_application_status(SimpleNamespace(status="approved"), grant, now=NOW) == (
        "upcoming",
        ["wait"],
    )


@pytest.mark.asyncio
async def test_status_unknown_identity_does_not_persist_user_binding_or_membership() -> None:
    class Verifier:
        async def verify(self, token):
            return "Uunknown"

    class Repository:
        organization_id = uuid4()
        added = []

        async def policy(self):
            return SimpleNamespace(applications_enabled=True)

        async def applications_for_user(self, user_id):
            raise AssertionError("unknown identity must not query applicant history")

    class Identity:
        async def get_line_binding(self, line_user_id):
            return None

        async def get_organization(self, organization_id):
            return SimpleNamespace(id=organization_id, name="測試收容所", status="active")

    service = VolunteerAccessService(Repository(), Identity(), Verifier())
    response = await service.status(id_token="token", entry_reference_id=uuid4())

    assert response.effective_status == "none"
    assert response.application is None
    assert Repository.added == []


def test_entry_purpose_is_fixed_and_blank_reference_is_rejected() -> None:
    assert ENTRY_REFERENCE_PURPOSE == "volunteer_application_entry"
    with pytest.raises(DomainError, match="入口"):
        VolunteerAccessService.validate_entry_reference("")
