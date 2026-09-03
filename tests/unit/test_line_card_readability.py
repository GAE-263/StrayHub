"""卡片要能被讀懂：文字看得清楚、長字串不被切掉、分隔線底下有東西。

這三件事都不會讓程式壞掉，所以沒有測試就沒人會發現：對比度 3:1 的灰字在手機
戶外光線下等於沒有、`baseline` 版面會把長區域名截斷成「後山區…」、沒有按鈕的
卡片結尾掛著一條什麼都沒分隔到的線。志工在收容所現場用的就是這些卡片。
"""

from __future__ import annotations

from services.api.app.application import line_message_presenter as presenter
from services.api.app.application.line_message_presenter import (
    BUTTER,
    INK,
    INK_SOFT,
    SURFACE,
    prompt_bubble,
    summary_bubble,
)


def _relative_luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    first, second = _relative_luminance(foreground), _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _nodes(node, predicate) -> list[dict]:
    if isinstance(node, dict):
        found = [node] if predicate(node) else []
        for value in node.values():
            found.extend(_nodes(value, predicate))
        return found
    if isinstance(node, list):
        return [item for child in node for item in _nodes(child, predicate)]
    return []


def test_secondary_ink_is_readable_on_the_paper_it_is_printed_on() -> None:
    # AA 對小字的門檻是 4.5:1；卡片內文與欄位標籤都用這個顏色。
    assert _contrast(INK_SOFT, SURFACE) >= 4.5


def test_the_header_caption_is_not_grey_on_a_saturated_tone() -> None:
    """標頭底色是彩色的，副標若沿用淺灰會掉到 2.3:1，比標題還難讀。"""
    bubble = prompt_bubble(
        title="是 小黑 嗎？", caption="散步回報 · 請確認動物", body_text="請確認", choices=[]
    )
    header = bubble["contents"]["header"]
    caption = header["contents"][0]["contents"][1]["contents"][0]
    assert caption["text"] == "散步回報 · 請確認動物"
    assert caption["color"] == INK
    assert _contrast(caption["color"], BUTTER) > _contrast(INK_SOFT, BUTTER)


def test_a_card_without_buttons_does_not_end_on_a_separator() -> None:
    bubble = prompt_bubble(
        title="照片處理失敗", caption="散步回報", body_text="請重新傳送", choices=[]
    )
    assert _nodes(bubble, lambda node: node.get("type") == "separator") == []


def test_a_card_with_buttons_still_separates_them_from_the_text() -> None:
    bubble = prompt_bubble(
        title="還有一筆回報沒送出",
        caption="散步回報",
        body_text="要換一隻嗎？",
        choices=[("繼續回報 小黑", "action=resume_draft", "↩")],
    )
    assert _nodes(bubble, lambda node: node.get("type") == "separator")


def test_a_long_area_name_wraps_instead_of_being_cut_off() -> None:
    """`baseline` 版面會忽略 wrap 並把溢出的字省略掉，`horizontal` 才會換行。"""
    row = presenter._info_row("📍", "所在區域", "後山第三犬舍 B 區 靠近醫療室那排")
    assert row["layout"] == "horizontal"
    value = row["contents"][-1]
    assert value["wrap"] is True


def test_a_long_answer_wraps_in_the_summary_too() -> None:
    bubble = summary_bubble(
        [("🐾", "步態", "後左腳明顯拖行，走幾步就停下來舔腳掌")],
        note=None,
        choices=[],
        animal_name="小黑",
    )
    rows = _nodes(bubble, lambda node: node.get("layout") in {"baseline", "horizontal"})
    assert all(row["layout"] != "baseline" for row in rows)
