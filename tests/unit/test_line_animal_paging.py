"""可回報動物的清單不該靜默丟掉任何一隻。

原本 `_reportable_animals` 以 `[:6]` 切掉多餘的動物，沒有任何提示。志工今天若
被派了 8 隻，他只會看到 6 隻，剩下 2 隻在介面上完全不存在——他會以為今天就是
這 6 隻。在收容所現場，那是靜默漏掉的照護紀錄。
"""

from __future__ import annotations

from urllib.parse import parse_qs
from uuid import UUID, uuid4

from services.api.app.api.line_webhook import (
    _SELECTION_PAGE,
    _animal_label,
    _offset_value,
    _reportable_animals,
)


class _Animal:
    def __init__(self, name: str, shelter_number: str | None = None) -> None:
        self.id = uuid4()
        self.name = name
        self.shelter_number = shelter_number


def _animals(count: int) -> list[_Animal]:
    return [_Animal(f"毛孩{index:02d}", f"A{index:03d}") for index in range(count)]


def _data(item: dict) -> dict[str, str]:
    return {key: value[0] for key, value in parse_qs(item["action"]["data"]).items()}


def _selected_ids(items: list[dict]) -> list[str]:
    return [_data(item)["animal_id"] for item in items if _data(item)["action"] == "select_animal"]


def _more_item(items: list[dict]) -> dict | None:
    return next((item for item in items if _data(item)["action"] == "more_animals"), None)


def test_a_short_list_is_shown_whole_without_a_more_button() -> None:
    items = _reportable_animals(_animals(5))
    assert len(_selected_ids(items)) == 5
    assert _more_item(items) is None


def test_a_long_list_is_paged_rather_than_cut_off() -> None:
    animals = _animals(20)
    items = _reportable_animals(animals)
    # LINE 只收 13 個 quick reply，最後一格留給「更多」。
    assert len(items) == _SELECTION_PAGE + 1
    assert len(_selected_ids(items)) == _SELECTION_PAGE
    more = _more_item(items)
    assert more is not None
    assert _data(more)["offset"] == str(_SELECTION_PAGE)
    # 志工必須知道還有多少隻，否則他無從得知自己看到的是不是全部。
    assert "8" in more["action"]["label"]


def test_every_animal_is_reachable_by_walking_the_pages() -> None:
    animals = _animals(30)
    seen: list[str] = []
    offset = 0
    for _ in range(10):
        items = _reportable_animals(animals, offset=offset)
        seen.extend(_selected_ids(items))
        more = _more_item(items)
        if more is None:
            break
        offset = int(_data(more)["offset"])
    assert seen == [str(animal.id) for animal in animals]


def test_the_last_page_does_not_offer_more() -> None:
    animals = _animals(20)
    items = _reportable_animals(animals, offset=_SELECTION_PAGE)
    assert len(_selected_ids(items)) == 8
    assert _more_item(items) is None


def test_the_draft_token_survives_paging() -> None:
    animals = _animals(20)
    items = _reportable_animals(animals, offset=0, draft_token="tok-123")
    assert all(_data(item)["draft_token"] == "tok-123" for item in items)
    more = _more_item(items)
    assert more is not None
    # 換動物的流程分頁後仍必須回到同一份草稿。
    assert _data(more)["draft_token"] == "tok-123"


def test_an_offset_past_the_end_yields_nothing_rather_than_wrapping() -> None:
    # 呼叫端會據此重新從頭開始，而不是顯示一張空白清單。
    assert _reportable_animals(_animals(5), offset=99) == []


def test_label_names_the_animal_and_its_shelter_number() -> None:
    assert _animal_label(_Animal("小黑", "VAAAG114")) == "小黑／VAAAG114"
    assert _animal_label(_Animal("小白", None)) == "小白／無收容編號"


def test_quick_reply_labels_stay_within_the_line_limit() -> None:
    items = _reportable_animals([_Animal("名字特別長的一隻米克斯犬", "VAAAG114080610")] * 1)
    assert all(len(item["action"]["label"]) <= 20 for item in items)


def test_offsets_from_postback_data_are_treated_as_untrusted() -> None:
    assert _offset_value("12") == 12
    assert _offset_value("") == 0
    assert _offset_value("-5") == 0
    assert _offset_value("../../etc") == 0
    assert _offset_value(None) == 0


def test_uuid_is_the_identity_carried_in_the_postback() -> None:
    animal = _Animal("小黑", "A001")
    items = _reportable_animals([animal])
    assert UUID(_selected_ids(items)[0]) == animal.id
