from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.animal_selection import (
    AnimalSelectionService,
    FindAnimalAction,
    issue_animal_confirmation_token,
    verify_animal_confirmation_token,
)


def test_find_animal_hub_has_exact_delivery_neutral_actions() -> None:
    assert list(FindAnimalAction) == [
        FindAnimalAction.QR,
        FindAnimalAction.SEARCH,
        FindAnimalAction.TODAY,
    ]


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
@pytest.mark.parametrize("query", [None, "小"])
async def test_scope_free_volunteer_list_and_search_return_active_tenant_animals(query) -> None:
    organization_id = uuid4()
    membership_id = uuid4()
    first = SimpleNamespace(id=uuid4(), name="小黑", status="active")
    second = SimpleNamespace(id=uuid4(), name="小白", status="active")

    class Animals:
        async def list_active_with_area(self):
            return [(first, None), (second, None)]

        async def search_with_area(self, value):
            assert value == "小"
            return [(first, None), (second, None)]

    class QrCodes:
        pass

    class Authorization:
        async def authorize(self, **_kwargs):
            return SimpleNamespace(animal=None)

    service = AnimalSelectionService(Animals(), QrCodes(), Authorization())
    result = await service.list_candidates(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=membership_id,
        role="VOLUNTEER",
        query=query,
    )
    assert [candidate.animal.id for candidate in result] == [first.id, second.id]


@pytest.mark.asyncio
async def test_scope_free_qr_resolve_and_confirmation_succeed() -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(id=uuid4(), organization_id=organization_id, status="active")
    qr = SimpleNamespace(animal_id=animal.id, organization_id=organization_id)

    class Animals:
        async def get_with_area(self, animal_id):
            return (animal, None) if animal_id == animal.id else None

    class QrCodes:
        async def resolve(self, raw_token):
            return qr if raw_token == "valid-token" else None

    class Authorization:
        async def authorize(self, **_kwargs):
            return SimpleNamespace(animal=animal)

    service = AnimalSelectionService(Animals(), QrCodes(), Authorization())

    resolved = await service.resolve_qr(
        raw_token="valid-token",
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        role="VOLUNTEER",
    )
    confirmed = await service.confirm(
        animal_id=animal.id,
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        role="VOLUNTEER",
    )

    assert resolved.animal is animal
    assert confirmed.animal is animal


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["tampered-token", "revoked-token"])
async def test_unresolved_or_revoked_qr_fails_without_animal_details(token) -> None:
    class Animals:
        pass

    class QrCodes:
        async def resolve(self, _raw_token):
            return None

    class Authorization:
        async def authorize(self, **_kwargs):
            raise AssertionError("Unresolved QR must not reach animal authorization")

    with pytest.raises(DomainError) as error:
        await AnimalSelectionService(Animals(), QrCodes(), Authorization()).resolve_qr(
            raw_token=token,
            user_id=uuid4(),
            organization_id=uuid4(),
            membership_id=uuid4(),
            role="VOLUNTEER",
        )

    assert error.value.code == "animal_not_found"
    assert "id" not in error.value.message.lower()


@pytest.mark.asyncio
async def test_qr_from_other_organization_fails_before_animal_lookup() -> None:
    current_organization_id = uuid4()

    class Animals:
        pass

    class QrCodes:
        async def resolve(self, _raw_token):
            return SimpleNamespace(animal_id=uuid4(), organization_id=uuid4())

    class Authorization:
        async def authorize(self, **_kwargs):
            raise AssertionError("Foreign QR must not reach animal authorization")

    with pytest.raises(DomainError) as error:
        await AnimalSelectionService(Animals(), QrCodes(), Authorization()).resolve_qr(
            raw_token="foreign-token",
            user_id=uuid4(),
            organization_id=current_organization_id,
            membership_id=uuid4(),
            role="VOLUNTEER",
        )

    assert error.value.code == "animal_not_found"


@pytest.mark.asyncio
async def test_search_page_preserves_query_and_has_more_metadata() -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(id=uuid4(), organization_id=organization_id, status="active")

    class Animals:
        async def search_with_area_page(self, query, *, offset, limit):
            assert (query, offset, limit) == ("  A-0  ", 2, 2)
            return [(animal, None)], 5

    class Authorization:
        async def authorize(self, **_kwargs):
            return SimpleNamespace()

    page = await AnimalSelectionService(Animals(), object(), Authorization()).search_page(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        role="VOLUNTEER",
        query="  A-0  ",
        page=2,
        page_size=2,
    )
    assert page.total == 5
    assert page.has_more is True
    assert page.items[0].animal is animal


def test_three_entry_points_share_confirmation_projection() -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        name="小黑",
        shelter_number="A-01",
        current_photo_key="org/photo.jpg",
    )
    area = SimpleNamespace(name="A區")
    from services.api.app.application.animal_selection import AnimalCandidate

    confirmation = AnimalCandidate(animal, area).confirmation(organization_name="浪浪之家")
    assert confirmation.organization_id == organization_id
    assert confirmation.organization_name == "浪浪之家"
    assert confirmation.photo_reference == "org/photo.jpg"
