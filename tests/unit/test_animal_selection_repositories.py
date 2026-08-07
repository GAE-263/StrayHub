from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.qr_token_service import QrTokenService
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return iter(self.value)


class _Session:
    def __init__(self, result):
        self.result = result

    async def execute(self, _statement):
        return _Result(self.result)

    def add(self, _value):
        return None

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_animal_repository_lists_only_active_animals() -> None:
    organization_id = uuid4()
    active = SimpleNamespace(id=uuid4(), name="小黑", shelter_number="A-01", status="active")
    repository = AnimalRepository(_Session([active]), organization_id)

    result = await repository.list_active()

    assert result == [active]


@pytest.mark.asyncio
async def test_qr_token_service_rejects_animal_from_other_organization() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    qr = SimpleNamespace(
        id=uuid4(),
        animal_id=animal_id,
        organization_id=organization_id,
    )
    animal = SimpleNamespace(id=animal_id, organization_id=uuid4(), status="active")
    service = QrTokenService(
        AnimalRepository(_Session(animal), organization_id),
        QrCodeRepository(_Session(qr), organization_id),
    )

    with pytest.raises(Exception, match="無法存取其他收容所資料"):
        await service.resolve(raw_token="not-a-real-token")
