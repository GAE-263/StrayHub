from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.observation_option_service import ObservationOptionService
from services.api.app.persistence.models.observation import ObservationCategory


class FakeObservationRepository:
    def __init__(self):
        self.organization_id = uuid4()
        self.options = {}
        self.category = ObservationCategory(
            organization_id=None,
            code="emotion",
            display_name="情緒",
            description="",
            status="active",
        )

    async def get_category(self, _category_id):
        return self.category

    async def option_code_exists(self, code):
        return any(option.code == code for option in self.options.values())

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


@pytest.mark.asyncio
async def test_code_must_be_unique_and_reorder_only_updates_extensions() -> None:
    repository = FakeObservationRepository()
    service = ObservationOptionService(repository)
    first = await service.create(category_id=uuid4(), code="emotion.first", display_name="第一個")
    second = await service.create(category_id=uuid4(), code="emotion.second", display_name="第二個")
    with pytest.raises(DomainError, match="Code 已存在"):
        await service.create(category_id=uuid4(), code="emotion.first", display_name="重複")

    reordered = await service.reorder([second.id, first.id])
    assert [option.display_order for option in reordered] == [0, 1]
