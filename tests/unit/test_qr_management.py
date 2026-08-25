from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.api.qr_codes import _payload
from services.api.app.application.qr_token_service import (
    QrTokenService,
    issue_printable_qr_token,
)


class _Animals:
    def __init__(self, animal):
        self.animal = animal

    async def get(self, _animal_id):
        return self.animal


class _QrCodes:
    def __init__(self, organization_id, active=None, current=None):
        self.organization_id = organization_id
        self.active = active
        self.current = current
        self.created = []
        self.revoked = []
        self.locks = []

    async def lock_animal(self, animal_id):
        self.locks.append(animal_id)

    async def active_for_animal(self, _animal_id):
        return self.active

    async def get(self, _qr_id):
        return self.current

    async def create(self, value):
        self.created.append(value)
        return value

    async def revoke(self, qr_code_id):
        self.revoked.append(qr_code_id)
        self.current.status = "revoked"
        self.current.revoked = True
        return self.current


@pytest.mark.asyncio
async def test_create_reuses_current_active_qr_and_does_not_create_another() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    active = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        animal_id=animal_id,
        token_digest="legacy-digest",
        status="active",
        revoked=False,
    )
    repository = _QrCodes(organization_id, active=active)
    service = QrTokenService(
        _Animals(
            SimpleNamespace(
                id=animal_id,
                organization_id=organization_id,
                status="active",
            )
        ),
        repository,
    )

    qr_code, token = await service.create(animal_id=animal_id)

    assert qr_code is active
    assert token is None
    assert repository.created == []
    assert repository.locks == [animal_id]


@pytest.mark.asyncio
async def test_create_issues_reprintable_opaque_token_for_active_animal() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    repository = _QrCodes(organization_id)
    service = QrTokenService(
        _Animals(
            SimpleNamespace(
                id=animal_id,
                organization_id=organization_id,
                status="active",
            )
        ),
        repository,
    )

    qr_code, token = await service.create(animal_id=animal_id)

    assert token == issue_printable_qr_token(qr_code.id)
    assert str(qr_code.id) not in token
    assert str(animal_id) not in token
    assert _payload(qr_code)["deep_link"].endswith(f"qr_token={token}")


@pytest.mark.asyncio
async def test_create_rejects_inactive_or_cross_tenant_animal() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    for animal in (
        SimpleNamespace(
            id=animal_id,
            organization_id=organization_id,
            status="inactive",
        ),
        SimpleNamespace(
            id=animal_id,
            organization_id=uuid4(),
            status="active",
        ),
    ):
        service = QrTokenService(_Animals(animal), _QrCodes(organization_id))
        with pytest.raises(DomainError) as error:
            await service.create(animal_id=animal_id)
        assert error.value.code == "animal_not_found"


@pytest.mark.asyncio
async def test_regenerate_revokes_old_record_and_creates_new_active_qr() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    current = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        animal_id=animal_id,
        token_digest="old-digest",
        status="active",
        revoked=False,
    )
    repository = _QrCodes(organization_id, active=current, current=current)
    service = QrTokenService(
        _Animals(
            SimpleNamespace(
                id=animal_id,
                organization_id=organization_id,
                status="active",
            )
        ),
        repository,
    )

    replacement, token = await service.regenerate(qr_code_id=current.id)

    assert repository.revoked == [current.id]
    assert replacement.id != current.id
    assert replacement.status == "active"
    assert token == issue_printable_qr_token(replacement.id)
