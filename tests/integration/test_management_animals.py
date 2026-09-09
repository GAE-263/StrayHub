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
    def __init__(
        self, *, animal_id=None, organization_id=None, checksum=None, media_overrides=None
    ):
        self.animal_id = animal_id or uuid4()
        self.organization_id = organization_id or uuid4()
        self.checksum = checksum
        self.media_overrides = media_overrides or {}
        self.statements = []

    async def scalar(self, _query):
        return 1

    async def execute(self, query):
        self.statements.append(query)
        animal = SimpleNamespace(
            id=self.animal_id,
            organization_id=self.organization_id,
            name="小森",
            shelter_number="A-001",
            current_photo_key="animals/a/primary.jpg" if self.checksum else None,
            status="active",
            species=None,
            breed=None,
            size=None,
            energy=None,
            temperament=[],
            is_adoptable=False,
            adoption_notes=None,
        )
        area = SimpleNamespace(id=uuid4(), name="A Cage", area_type="cage")
        media = None
        if self.checksum:
            media_values = {
                "organization_id": self.organization_id,
                "object_key": animal.current_photo_key,
                "status": "processed",
                "exif_removed": True,
                "content_type": "image/jpeg",
                "checksum": self.checksum,
            }
            media_values.update(self.media_overrides)
            media = SimpleNamespace(**media_values)
        return _Result([(animal, area, media)])


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
    assert result["items"][0]["photo_url"] is None


@pytest.mark.asyncio
async def test_management_animal_list_versions_current_valid_photo_by_checksum() -> None:
    organization_id, animal_id = uuid4(), uuid4()
    old_checksum = "a" * 64
    new_checksum = "b" * 64

    old_result = await ManagementAnimalService(
        _Session(
            animal_id=animal_id,
            organization_id=organization_id,
            checksum=old_checksum,
        ),
        organization_id,
    ).list(query=None, area_id=None, status="active", page=1, page_size=20)
    new_result = await ManagementAnimalService(
        _Session(
            animal_id=animal_id,
            organization_id=organization_id,
            checksum=new_checksum,
        ),
        organization_id,
    ).list(query=None, area_id=None, status="active", page=1, page_size=20)

    assert old_result["items"][0]["photo_url"] == (
        f"/v1/management/animals/{animal_id}/photo?v={old_checksum}"
    )
    assert new_result["items"][0]["photo_url"] == (
        f"/v1/management/animals/{animal_id}/photo?v={new_checksum}"
    )


@pytest.mark.asyncio
async def test_management_animal_list_photo_version_join_is_tenant_scoped() -> None:
    organization_id = uuid4()
    session = _Session(organization_id=organization_id, checksum="a" * 64)

    await ManagementAnimalService(session, organization_id).list(
        query=None,
        area_id=None,
        status="active",
        page=1,
        page_size=20,
    )

    sql = " ".join(str(session.statements[0]).lower().split())
    assert "animals.organization_id" in sql
    assert "media_assets.organization_id" in sql
    assert (
        "animals.current_photo_key = media_assets.object_key" in sql
        or "media_assets.object_key = animals.current_photo_key" in sql
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "media_overrides",
    [
        {"status": "pending"},
        {"exif_removed": False},
        {"content_type": "image/svg+xml"},
    ],
)
async def test_management_animal_list_omits_invalid_current_photo(media_overrides) -> None:
    organization_id = uuid4()
    result = await ManagementAnimalService(
        _Session(
            organization_id=organization_id,
            checksum="a" * 64,
            media_overrides=media_overrides,
        ),
        organization_id,
    ).list(query=None, area_id=None, status="active", page=1, page_size=20)

    assert result["items"][0]["photo_url"] is None


@pytest.mark.asyncio
async def test_management_animal_detail_hides_missing_resource() -> None:
    class EmptySession(_Session):
        async def execute(self, _query):
            return _Result([])

    service = ManagementAnimalService(EmptySession(), uuid4())
    with pytest.raises(Exception, match="動物不存在"):
        await service.get(uuid4())
