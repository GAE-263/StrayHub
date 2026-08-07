from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import (
    AnimalSelectionService,
    issue_animal_confirmation_token,
    verify_animal_confirmation_token,
)


def test_animal_confirmation_token_is_bound_to_actor_session_and_animal() -> None:
    values = {
        "user_id": uuid4(),
        "organization_id": uuid4(),
        "membership_id": uuid4(),
        "session_id": uuid4(),
        "animal_id": uuid4(),
    }
    token = issue_animal_confirmation_token(**values)
    verify_animal_confirmation_token(token, **values)
    with pytest.raises(DomainError, match="確認回報的動物"):
        verify_animal_confirmation_token(token, **{**values, "animal_id": uuid4()})
    with pytest.raises(DomainError, match="確認回報的動物"):
        verify_animal_confirmation_token("not-a-valid-token", **values)


@pytest.mark.asyncio
async def test_volunteer_selection_is_limited_to_current_reportable_scope() -> None:
    allowed = SimpleNamespace(id=uuid4(), name="小黑", status="active")
    excluded = SimpleNamespace(id=uuid4(), name="小白", status="active")

    class Animals:
        async def list_active_with_area(self):
            return [(allowed, None), (excluded, None)]

    class QrCodes:
        pass

    class Scopes:
        async def active_animal_ids(self, *, volunteer_user_id):
            return {allowed.id}

    service = AnimalSelectionService(Animals(), QrCodes(), Scopes())
    result = await service.list_candidates(user_id=uuid4(), role="VOLUNTEER")
    assert [candidate.animal.id for candidate in result] == [allowed.id]
