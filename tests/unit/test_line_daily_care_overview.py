"""「今日照護毛孩」要回答「今天誰還沒被照顧」，不是再問一次要回報哪一隻。

在此之前，這顆按鈕與「開始照護回報」跑的是同一段程式碼，回覆逐字相同。四格選單
裡有兩格做同一件事，志工得自己猜差異在哪。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs
from uuid import uuid4

import pytest
from services.api.app.api.line_webhook import _OVERVIEW_PAGE, _daily_care_overview


class _Animal:
    def __init__(self, name: str, shelter_number: str) -> None:
        self.id = uuid4()
        self.name = name
        self.shelter_number = shelter_number


class _ScopeRepositoryStub:
    def __init__(self, animals: list[_Animal]) -> None:
        self._animals = animals

    async def active_animals(self, *, volunteer_user_id, now=None):
        return self._animals


class _CareReportRepositoryStub:
    def __init__(self, submitted: dict) -> None:
        self.submitted = submitted
        self.window: tuple[datetime, datetime] | None = None

    async def latest_submission_by_animal(self, *, start, end):
        self.window = (start, end)
        return self.submitted


class _SessionStub:
    """Only the organization lookup goes through the session directly."""

    def __init__(self, organization) -> None:
        self._organization = organization

    async def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self._organization)


def _install(monkeypatch, animals, submitted):
    import services.api.app.api.line_webhook as webhook

    reports = _CareReportRepositoryStub(submitted)
    monkeypatch.setattr(
        webhook,
        "ReportableScopeRepository",
        lambda session, organization_id: _ScopeRepositoryStub(animals),
    )
    monkeypatch.setattr(webhook, "CareReportRepository", lambda session, organization_id: reports)
    return reports


def _bubble(messages):
    assert len(messages) == 1
    return messages[0]


def _rows(bubble):
    return bubble["contents"]["body"]["contents"]


def _row_texts(row):
    return [item["text"] for item in row["contents"][1]["contents"]]


ORGANIZATION = SimpleNamespace(id=uuid4(), timezone="Asia/Taipei")
SESSION = _SessionStub(ORGANIZATION)


@pytest.mark.asyncio
async def test_nothing_to_care_for_says_so_plainly(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, [], {})
    messages = await _daily_care_overview(SESSION, uuid4(), uuid4())
    assert len(messages) == 1
    assert messages[0]["type"] == "flex"
    assert "今日目前沒有可回報的動物" in messages[0]["altText"]


@pytest.mark.asyncio
async def test_each_animal_shows_whether_today_is_done(monkeypatch: pytest.MonkeyPatch) -> None:
    cared, pending = _Animal("小黑", "A001"), _Animal("小白", "A002")
    _install(
        monkeypatch,
        [cared, pending],
        {cared.id: datetime(2026, 8, 21, 6, 26, tzinfo=timezone.utc)},
    )
    bubble = _bubble(await _daily_care_overview(SESSION, uuid4(), uuid4()))
    rows = _rows(bubble)
    assert _row_texts(rows[0]) == ["小黑／A001", "已回報 · 14:26"]
    assert _row_texts(rows[1]) == ["小白／A002", "尚未回報"]
    # 勾與空格是掃一眼就能分辨的差別，顏色不是。
    assert rows[0]["contents"][0]["text"] == "✅"
    assert rows[1]["contents"][0]["text"] == "⬜"


@pytest.mark.asyncio
async def test_the_time_shown_is_the_shelter_s_local_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    animal = _Animal("小黑", "A001")
    _install(monkeypatch, [animal], {animal.id: datetime(2026, 8, 21, 16, 5, tzinfo=timezone.utc)})
    bubble = _bubble(await _daily_care_overview(SESSION, uuid4(), uuid4()))
    # 16:05 UTC 在台北是隔天 00:05；志工看的是自己的時鐘。
    assert _row_texts(_rows(bubble)[0])[1] == "已回報 · 00:05"


@pytest.mark.asyncio
async def test_the_day_window_follows_the_shelter_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    animal = _Animal("小黑", "A001")
    reports = _install(monkeypatch, [animal], {})
    await _daily_care_overview(SESSION, uuid4(), uuid4())
    start, end = reports.window
    # 台北的一天從 UTC 16:00 起算，不是 UTC 午夜。
    assert (start.hour, end.hour) == (16, 16)
    assert (end - start).total_seconds() == 24 * 3600


@pytest.mark.asyncio
async def test_counts_describe_the_whole_day_not_the_visible_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    animals = [_Animal(f"毛孩{index:02d}", f"A{index:03d}") for index in range(20)]
    submitted = {
        animal.id: datetime(2026, 8, 21, 6, 0, tzinfo=timezone.utc) for animal in animals[:15]
    }
    _install(monkeypatch, animals, submitted)
    bubble = _bubble(await _daily_care_overview(SESSION, uuid4(), uuid4()))
    caption = bubble["contents"]["header"]["contents"][0]["contents"][1]["contents"][0]["text"]
    # 只看得到 8 隻，但今天有 20 隻、已回報 15 隻——分頁不該讓志工誤以為工作快做完了。
    assert caption == "共 20 隻 · 已回報 15 隻"
    assert bubble["altText"] == "🐾 今日照護毛孩（已回報 15 / 20）"


@pytest.mark.asyncio
async def test_a_long_day_is_paged_and_says_how_many_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    animals = [_Animal(f"毛孩{index:02d}", f"A{index:03d}") for index in range(20)]
    _install(monkeypatch, animals, {})
    bubble = _bubble(await _daily_care_overview(SESSION, uuid4(), uuid4()))
    rows = _rows(bubble)
    assert len(rows) == _OVERVIEW_PAGE + 1
    more = rows[-1]
    assert "還有 12 隻" in more["contents"][0]["text"]
    assert parse_qs(more["action"]["data"])["offset"] == [str(_OVERVIEW_PAGE)]


@pytest.mark.asyncio
async def test_the_last_page_does_not_offer_more(monkeypatch: pytest.MonkeyPatch) -> None:
    animals = [_Animal(f"毛孩{index:02d}", f"A{index:03d}") for index in range(10)]
    _install(monkeypatch, animals, {})
    bubble = _bubble(await _daily_care_overview(SESSION, uuid4(), uuid4(), offset=_OVERVIEW_PAGE))
    rows = _rows(bubble)
    assert len(rows) == 2
    assert all(
        "action" in row and parse_qs(row["action"]["data"])["action"] == ["select_animal"]
        for row in rows
    )


@pytest.mark.asyncio
async def test_tapping_an_animal_starts_a_report_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    animal = _Animal("小黑", "A001")
    _install(monkeypatch, [animal], {})
    bubble = _bubble(await _daily_care_overview(SESSION, uuid4(), uuid4()))
    data = parse_qs(_rows(bubble)[0]["action"]["data"])
    assert data["action"] == ["select_animal"]
    assert data["animal_id"] == [str(animal.id)]
