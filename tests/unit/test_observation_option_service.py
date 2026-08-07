from uuid import uuid4

import pytest
from services.api.app.application.observation_option_service import ObservationOptionService


class FakeObservationRepository:
    def __init__(self):
        self.organization_id = uuid4()
        self.options = {}

    async def add_option(self, option):
        option.id = uuid4()
        self.options[option.id] = option
        return option

    async def get_option(self, option_id):
        return self.options.get(option_id)


@pytest.mark.asyncio
async def test_option_rename_keeps_code_and_disable_keeps_history() -> None:
    repository = FakeObservationRepository()
    service = ObservationOptionService(repository)
    option = await service.create(category_id=uuid4(), code="emotion.calm", display_name="平靜")

    await service.update(option.id, display_name="平靜／放鬆")
    await service.disable(option.id)

    assert option.code == "emotion.calm"
    assert option.status == "disabled"
