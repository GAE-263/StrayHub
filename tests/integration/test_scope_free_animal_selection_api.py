from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api import animal_selection
from services.api.app.api.animal_selection import QrResolveRequest
from services.api.app.api.dependencies import RequestContext
from services.api.app.application.animal_selection import (
    AnimalCandidate,
    verify_animal_confirmation_token,
)


@pytest.mark.asyncio
async def test_scope_free_qr_resolve_and_confirm_endpoints_issue_bound_token(
    monkeypatch,
) -> None:
    user_id = uuid4()
    organization_id = uuid4()
    membership_id = uuid4()
    session_id = uuid4()
    animal_id = uuid4()
    animal = SimpleNamespace(
        id=animal_id,
        organization_id=organization_id,
        name="Scope-free Animal",
        shelter_number="QR-001",
        current_photo_key=None,
        status="active",
        sex="female",
        breed="藏獒",
        care_guidance="請依現場安排餵食",
        behavior_notes="僅管理端可見",
    )
    candidate = AnimalCandidate(animal=animal, area=None)

    class Selection:
        async def resolve_qr(self, **kwargs):
            assert kwargs == {
                "raw_token": "valid-qr",
                "user_id": user_id,
                "organization_id": organization_id,
                "membership_id": membership_id,
                "role": "VOLUNTEER",
            }
            return candidate

        async def confirm(self, **kwargs):
            assert kwargs == {
                "animal_id": animal_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "membership_id": membership_id,
                "role": "VOLUNTEER",
            }
            return candidate

    monkeypatch.setattr(animal_selection, "_selection_service", lambda *_args: Selection())
    context = RequestContext(
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        role="VOLUNTEER",
        session_id=session_id,
    )

    resolved = await animal_selection.resolve_qr_token(
        QrResolveRequest(qr_token="valid-qr"), context, SimpleNamespace()
    )
    confirmed = await animal_selection.confirm_animal(animal_id, context, SimpleNamespace())

    assert resolved.id == animal_id
    assert confirmed.id == animal_id
    assert resolved.sex == "female"
    assert resolved.breed == "藏獒"
    assert confirmed.care_guidance == "請依現場安排餵食"
    assert "behavior_notes" not in resolved.model_dump()
    assert "behavior_notes" not in confirmed.model_dump()
    assert "medical_history" not in confirmed.model_dump()
    verify_animal_confirmation_token(
        confirmed.confirmation_token,
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        session_id=session_id,
        animal_id=animal_id,
    )
