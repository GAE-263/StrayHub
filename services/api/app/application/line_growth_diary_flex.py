"""Pure LINE Flex Message JSON builders for growth-diary: the "which pet"
picker, the periodic reminder push, the AI analysis reply, and the history
review carousel — same visual language as line_adoption_flex.py (reusing its
`_pill_row`/`_accent_bar`/`_PALETTE` rather than duplicating that styling
logic, since these are generic UI helpers, not adoption-domain ones), kept in
its own module since growth diary is a separate domain flow from adoption
matching."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from services.api.app.application.line_adoption_flex import _PALETTE, _accent_bar, _pill_row
from services.api.app.application.line_menu_actions import back_to_default_menu_quick_reply_item

_BORDER_COLOR = "#716053"
_CARD_BG = "#FAF6EE"
_TEXT_COLOR = "#716053"
_ACCENT_COLOR = "#716053"
_REMINDER_ACCENT = _PALETTE[1]  # 鼠尾草綠，跟毛孩日記選單既有的用色一致


@dataclass(frozen=True)
class AdoptedAnimalOption:
    inquiry_id: str
    animal_name: str
    shelter_number: str | None


def growth_diary_quick_reply_items(*, include_back_to_default: bool = False) -> list[dict]:
    """Build diary actions, optionally including the canonical flow-exit action."""
    items = [
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": "新增一篇",
                "data": urlencode({"action": "start_growth_diary_entry", "flow": "growth_diary"}),
                "displayText": "新增一篇",
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": "日記回顧",
                "data": urlencode({"action": "view_growth_diary_history", "flow": "growth_diary"}),
                "displayText": "日記回顧",
            },
        },
    ]
    if include_back_to_default:
        items.append(back_to_default_menu_quick_reply_item())
    return items


def build_animal_picker(options: list[AdoptedAnimalOption]) -> dict:
    bubbles = [_bubble(option) for option in options[:12]]
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {"type": "flex", "altText": "今天想記錄哪隻毛孩呢？🐾", "contents": contents}


def _bubble(option: AdoptedAnimalOption) -> dict:
    return {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": _CARD_BG,
            "borderColor": _BORDER_COLOR,
            "borderWidth": "medium",
            "cornerRadius": "lg",
            "paddingAll": "md",
            "spacing": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": f"🐾 {option.animal_name}．{option.shelter_number or '你的寶貝'}",
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                },
                {
                    "type": "button",
                    "style": "primary",
                    "color": _ACCENT_COLOR,
                    "margin": "md",
                    "action": {
                        "type": "postback",
                        "label": "寫日記囉 📔",
                        "data": urlencode(
                            {
                                "action": "select_growth_diary_animal",
                                "flow": "growth_diary",
                                "value": option.inquiry_id,
                            }
                        ),
                        "displayText": f"記錄{option.animal_name}的成長日記",
                    },
                },
            ],
        },
    }


def build_growth_diary_reminder_card(*, inquiry_id: str, animal_name: str, since_days: int) -> dict:
    """Pushed by the worker's periodic reminder (see
    growth_diary_reminder_handler.py) — "現在分享" reuses the exact same
    select_growth_diary_animal postback the picker/menu entry points use, so
    tapping it needs no new action handler; "晚點提醒我" just pushes the
    cadence clock forward without starting a pending draft."""
    _, accent = _REMINDER_ACCENT
    bubble: dict = {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": _CARD_BG,
            "borderColor": _BORDER_COLOR,
            "borderWidth": "medium",
            "cornerRadius": "lg",
            "paddingAll": "md",
            "spacing": "sm",
            "contents": [
                _accent_bar(accent),
                {
                    "type": "text",
                    "text": f"📔 好奇「{animal_name}」最近過得如何呀？",
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": (
                        f"已經 {since_days} 天沒有更新囉，分享一張近況照片，"
                        "或打幾句話讓我們知道近況吧 🐾"
                    ),
                    "size": "sm",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                },
                _pill_row(
                    {
                        "type": "postback",
                        "label": "現在分享",
                        "data": urlencode(
                            {
                                "action": "select_growth_diary_animal",
                                "flow": "growth_diary",
                                "value": inquiry_id,
                            }
                        ),
                        "displayText": "現在分享近況",
                    },
                    emoji="📔",
                    text="現在分享",
                    accent=accent,
                ),
                _pill_row(
                    {
                        "type": "postback",
                        "label": "晚點提醒我",
                        "data": urlencode(
                            {
                                "action": "snooze_growth_diary_reminder",
                                "flow": "growth_diary",
                                "value": inquiry_id,
                            }
                        ),
                        "displayText": "晚點提醒我",
                    },
                    emoji="⏰",
                    text="晚點提醒我",
                    accent=accent,
                    margin="sm",
                ),
            ],
        },
    }
    return {
        "type": "flex",
        "altText": f"好奇「{animal_name}」最近過得如何呀？",
        "contents": bubble,
        "quickReply": {"items": growth_diary_quick_reply_items()},
    }


_MOOD_HEADLINE = {
    "positive": "😊 聽起來狀況很不錯",
    "concern": "🩺 建議多留意一下",
    "neutral": "🐾 收到你的分享了",
}


def build_growth_diary_ai_reply_card(*, mood: str, reply_text: str) -> dict:
    _, accent = _REMINDER_ACCENT
    bubble: dict = {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": _CARD_BG,
            "borderColor": _BORDER_COLOR,
            "borderWidth": "medium",
            "cornerRadius": "lg",
            "paddingAll": "md",
            "spacing": "sm",
            "contents": [
                _accent_bar(accent),
                {
                    "type": "text",
                    "text": "🤖 AI 小幫手的回覆",
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": _MOOD_HEADLINE.get(mood, _MOOD_HEADLINE["neutral"]),
                    "size": "sm",
                    "color": _TEXT_COLOR,
                },
                {
                    "type": "text",
                    "text": reply_text,
                    "size": "sm",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                    "margin": "sm",
                },
            ],
        },
    }
    return {
        "type": "flex",
        "altText": "AI 小幫手回覆了你的毛孩日記",
        "contents": bubble,
        "quickReply": {"items": growth_diary_quick_reply_items(include_back_to_default=True)},
    }


@dataclass(frozen=True)
class GrowthDiaryHistoryEntry:
    date_label: str
    animal_name: str
    kind: str  # "photo" | "text"
    note: str | None
    mood: str | None
    reply: str | None
    photo_url: str | None = None


def build_growth_diary_history_carousel(entries: list[GrowthDiaryHistoryEntry]) -> dict:
    bubbles = [_history_bubble(entry) for entry in entries[:10]]
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {
        "type": "flex",
        "altText": "毛孩日記回顧",
        "contents": contents,
        "quickReply": {"items": growth_diary_quick_reply_items(include_back_to_default=True)},
    }


def _history_bubble(entry: GrowthDiaryHistoryEntry) -> dict:
    _, accent = _REMINDER_ACCENT
    body_contents: list[dict] = [
        _accent_bar(accent),
        {
            "type": "text",
            "text": f"🐾 {entry.date_label} 的紀錄",
            "weight": "bold",
            "size": "md",
            "wrap": True,
            "color": _TEXT_COLOR,
            "margin": "md",
        },
        {
            "type": "text",
            "text": _MOOD_HEADLINE.get(entry.mood or "neutral", _MOOD_HEADLINE["neutral"]),
            "size": "sm",
            "color": _TEXT_COLOR,
            "margin": "sm",
        },
    ]
    if entry.note:
        body_contents.append(
            {
                "type": "text",
                "text": f"「{entry.note}」",
                "size": "xs",
                "wrap": True,
                "color": _TEXT_COLOR,
                "margin": "sm",
            }
        )
    elif entry.kind == "photo":
        body_contents.append(
            {
                "type": "text",
                "text": "（這篇是照片紀錄，沒有留文字）",
                "size": "xs",
                "wrap": True,
                "color": _TEXT_COLOR,
                "margin": "sm",
            }
        )
    if entry.reply:
        body_contents.append(
            {
                "type": "text",
                "text": f"🤖 當時 AI 回覆：{entry.reply}",
                "size": "xs",
                "wrap": True,
                "color": _TEXT_COLOR,
                "margin": "sm",
            }
        )
    bubble: dict = {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": _CARD_BG,
            "borderColor": _BORDER_COLOR,
            "borderWidth": "medium",
            "cornerRadius": "lg",
            "paddingAll": "md",
            "spacing": "sm",
            "contents": body_contents,
        },
    }
    if entry.photo_url:
        bubble["hero"] = {
            "type": "image",
            "url": entry.photo_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        }
    return bubble
