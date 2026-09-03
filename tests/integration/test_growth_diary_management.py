from uuid import uuid4

import pytest
from services.api.app.persistence.repositories.growth_diary_repository import GrowthDiaryRepository


class _ReadResult:
    def scalar_one(self):
        return 0

    def one_or_none(self):
        return None

    def scalar_one_or_none(self):
        return None

    def all(self):
        return []


class _ReadSession:
    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _ReadResult()


def _sql(statement) -> str:
    return " ".join(str(statement).lower().split())


@pytest.mark.asyncio
async def test_management_count_list_detail_and_photo_are_explicitly_tenant_scoped() -> None:
    session = _ReadSession()
    repository = GrowthDiaryRepository(session, uuid4())

    await repository.count_for_management()
    await repository.list_for_management(page=1, page_size=50)
    await repository.get_for_management(uuid4())
    await repository.get_photo_for_management(uuid4())

    assert len(session.statements) == 4
    for statement in session.statements:
        assert "growth_diary_entries.organization_id" in _sql(statement)

    for statement in session.statements[1:3]:
        sql = _sql(statement)
        assert "animals.organization_id" in sql
        assert "adoption_inquiries.organization_id" in sql
        assert (
            "growth_diary_entries.animal_id = animals.id" in sql
            or "animals.id = growth_diary_entries.animal_id" in sql
        )
        assert (
            "growth_diary_entries.inquiry_id = adoption_inquiries.id" in sql
            or "adoption_inquiries.id = growth_diary_entries.inquiry_id" in sql
        )


@pytest.mark.asyncio
async def test_management_list_has_stable_newest_first_order() -> None:
    session = _ReadSession()

    await GrowthDiaryRepository(session, uuid4()).list_for_management(page=2, page_size=25)

    sql = _sql(session.statements[0])
    assert "growth_diary_entries.created_at desc" in sql
    assert "growth_diary_entries.id desc" in sql
    assert "limit" in sql and "offset" in sql


@pytest.mark.asyncio
async def test_management_search_is_trimmed_case_insensitive_and_tenant_scoped() -> None:
    session = _ReadSession()
    repository = GrowthDiaryRepository(session, uuid4())

    await repository.count_for_management(query="  MiGaO  ")
    await repository.list_for_management(
        page=1,
        page_size=20,
        query="  MiGaO  ",
    )

    assert len(session.statements) == 2
    for statement in session.statements:
        sql = _sql(statement)
        assert "growth_diary_entries.organization_id" in sql
        assert "animals.organization_id" in sql
        assert "lower(animals.name) like" in sql
        assert "lower(animals.shelter_number) like" in sql
        assert "migao" in str(statement.compile().params).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("mood", ["concern", "positive", "neutral"])
async def test_management_mood_filter_applies_before_count_and_page(mood: str) -> None:
    session = _ReadSession()
    repository = GrowthDiaryRepository(session, uuid4())

    await repository.count_for_management(mood=mood)
    await repository.list_for_management(page=3, page_size=10, mood=mood)

    count_sql, page_sql = (_sql(statement) for statement in session.statements)
    assert "growth_diary_entries.ai_mood" in count_sql
    assert "growth_diary_entries.ai_mood" in page_sql
    assert mood in str(session.statements[0].compile().params)
    assert mood in str(session.statements[1].compile().params)
    assert "limit" not in count_sql and "offset" not in count_sql
    assert "limit" in page_sql and "offset" in page_sql


@pytest.mark.asyncio
async def test_management_unanalyzed_means_no_valid_mood() -> None:
    session = _ReadSession()
    repository = GrowthDiaryRepository(session, uuid4())

    await repository.count_for_management(mood="unanalyzed")
    await repository.list_for_management(page=1, page_size=50, mood="unanalyzed")

    for statement in session.statements:
        assert "growth_diary_entries.ai_mood is null" in _sql(statement)
