from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.management_animal_service import ManagementAnimalService


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def one_or_none(self):
        return self.rows[0] if self.rows else None


class _Session:
    async def scalar(self, _query):
        return 1

    async def execute(self, _query):
        animal = SimpleNamespace(
            id=uuid4(),
            organization_id=uuid4(),
            name="小森",
            shelter_number="A-001",
            current_photo_key=None,
            status="active",
            species=None,
            breed=None,
            size=None,
            energy=None,
            temperament=None,
            is_adoptable=False,
            adoption_notes=None,
        )
        area = SimpleNamespace(id=uuid4(), name="A Cage", area_type="cage")
        return _Result([(animal, area)])


@pytest.mark.asyncio
async def test_management_animal_list_preserves_search_scope_and_area_summary() -> None:
    service = ManagementAnimalService(_Session(), uuid4())

    result = await service.list(
        query="A-001",
        area_id=None,
        status="active",
        page=1,
        page_size=20,
    )

    assert result["total"] == 1
    assert result["items"][0]["shelter_number"] == "A-001"
    assert result["items"][0]["area_name"] == "A Cage"


@pytest.mark.asyncio
async def test_management_animal_detail_hides_missing_resource() -> None:
    class EmptySession(_Session):
        async def execute(self, _query):
            return _Result([])

    service = ManagementAnimalService(EmptySession(), uuid4())
    with pytest.raises(Exception, match="動物不存在"):
        await service.get(uuid4())
