from uuid import uuid4

import pytest
from services.api.app.api.volunteer_access import _service_for_entry
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)


@pytest.mark.asyncio
async def test_entry_service_factory_accepts_resolver_public_context(monkeypatch) -> None:
    reference_id = uuid4()
    organization_id = uuid4()

    async def resolve_and_scope(_session, _raw_reference):
        return reference_id, organization_id, "ORG-A", "收容所 A"

    monkeypatch.setattr(VolunteerAccessRepository, "resolve_and_scope", resolve_and_scope)

    service, resolved_reference_id = await _service_for_entry(
        object(), "opaque-entry-reference", object()
    )

    assert resolved_reference_id == reference_id
    assert service.repository.organization_id == organization_id
