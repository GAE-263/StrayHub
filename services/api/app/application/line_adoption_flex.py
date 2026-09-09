"""Pure LINE Flex Message JSON builders for the adoption matching flow.

No I/O here — callers fetch data (shelters, animals, photo URLs, match
scores) and pass it in as the dataclasses below; these functions only shape
the Flex JSON. LINE Flex Message boxes support borderWidth/borderColor/
cornerRadius/backgroundColor but NOT boxShadow or custom fonts (text always
renders in the LINE client's system font).

Cards use a small rotating accent palette instead of one flat color — the
same four tones as the real Rich Menu region artwork (`infra/local/line-
rich-menu-region_select.jpg`: 北=珊瑚橘／中=鼠尾草綠／南=薰衣草紫／東=湖水
藍), also mirrored in `scripts/generate_rich_menu_image.py`'s
`ACCENT_PALETTE`. A shelter card picks its accent by the shelter's region;
a questionnaire card cycles through the same four by question topic, so
each new topic reads as visually distinct."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

_BORDER_COLOR = "#716053"
_CARD_BG = "#FAF6EE"
_TEXT_COLOR = "#716053"
_TRACK_COLOR = "#E2D8C8"

# (header/tint background, badge/bar accent) — same four tones as the real
# region Rich Menu artwork and scripts/generate_rich_menu_image.py's
# ACCENT_PALETTE, kept here too since this module has no import path to a
# script under scripts/.
_PALETTE: tuple[tuple[str, str], ...] = (
    ("#FCE2D6", "#E2836E"),  # 珊瑚橘（北區同款）
    ("#E3EDD3", "#84A75C"),  # 鼠尾草綠（中區同款）
    ("#E9DDF0", "#A47EC6"),  # 薰衣草紫（南區同款）
    ("#DCE9F3", "#6C9BC3"),  # 湖水藍（東區同款）
)

REGION_ACCENT: dict[str, tuple[str, str]] = {
    "north": _PALETTE[0],
    "central": _PALETTE[1],
    "south": _PALETTE[2],
    "east": _PALETTE[3],
}
_DEFAULT_ACCENT = _PALETTE[3]
_REPORT_ACCENT = _PALETTE[3]  # 適配報告卡固定用湖水藍，代表「總結」而非特定地區/主題


def _accent_bar(color: str) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "height": "6px",
        "cornerRadius": "xs",
        "backgroundColor": color,
        "margin": "none",
        "contents": [],
    }


def _pill_row(action: dict, *, emoji: str, text: str, accent: str, margin: str = "md") -> dict:
    """A tappable, thick-bordered row with a leading circular emoji badge —
    the button/option style shared by every card in this flow."""
    return {
        "type": "box",
        "layout": "horizontal",
        "borderColor": _BORDER_COLOR,
        "borderWidth": "medium",
        "cornerRadius": "lg",
        "paddingAll": "sm",
        "spacing": "sm",
        "alignItems": "center",
        "margin": margin,
        "action": action,
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "width": "28px",
                "height": "28px",
                "cornerRadius": "14px",
                "backgroundColor": accent,
                "justifyContent": "center",
                "alignItems": "center",
                "contents": [{"type": "text", "text": emoji, "size": "xs", "align": "center"}],
            },
            {
                "type": "text",
                "text": text,
                "color": _TEXT_COLOR,
                "weight": "bold",
                "wrap": True,
                "gravity": "center",
            },
        ],
    }


@dataclass(frozen=True)
class ShelterCard:
    organization_id: str
    name: str
    service_area: str | None
    adoptable_count: int
    region: str | None = None


def build_shelter_carousel(shelters: list[ShelterCard]) -> dict:
    bubbles = [_shelter_bubble(shelter) for shelter in shelters[:12]]
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {"type": "flex", "altText": "請選擇要領養的收容所", "contents": contents}


def _shelter_bubble(shelter: ShelterCard) -> dict:
    _, accent = REGION_ACCENT.get(shelter.region or "", _DEFAULT_ACCENT)
    area_line = (
        f"📍 {shelter.service_area or '地區未提供'}．"
        f"有 {shelter.adoptable_count} 隻毛孩在等一個家 🏡"
    )
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
                _accent_bar(accent),
                {
                    "type": "text",
                    "text": f"🏠 {shelter.name}",
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": area_line,
                    "size": "sm",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                },
                {
                    "type": "text",
                    "text": "每一隻都準備好被愛了 💛",
                    "size": "xs",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                },
                _pill_row(
                    {
                        "type": "postback",
                        "label": "看看這裡的毛孩",
                        "data": urlencode(
                            {
                                "action": "select_organization",
                                "flow": "adoption",
                                "value": shelter.organization_id,
                            }
                        ),
                        "displayText": f"選擇{shelter.name}",
                    },
                    emoji="🐾",
                    text="看看這裡的毛孩",
                    accent=accent,
                ),
            ],
        },
    }


@dataclass(frozen=True)
class MatchReportCard:
    animal_id: str
    name: str
    shelter_number: str | None
    photo_url: str | None
    score: int | None = None  # already a 0-100 percentage — see adoption_matching.score_percentage
    reasons: tuple[str, ...] = ()
    rank: int | None = None
    selectable: bool = False
    select_action: str = "select_matched_animal"
    select_label: str = "就決定是你了"


def build_match_report(cards: list[MatchReportCard], *, max_bubbles: int = 3) -> dict:
    """`max_bubbles` defaults to 3 (心有所屬's single-animal report, or its
    rule-based path never needing more) — the AI-curated 推薦名單 list and
    the low-score alternatives list (original + up to 3 AI picks) pass 5."""
    bubbles = [_report_bubble(card) for card in cards[:max_bubbles]]
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {"type": "flex", "altText": "幫你找到最適合的毛孩囉！🌟", "contents": contents}


def build_target_animal_picker(cards: list[MatchReportCard]) -> dict:
    """Browse-all-adoptable-animals carousel for `SELECTING_TARGET_ANIMAL` —
    reuses the same card visuals as `build_match_report` (`_report_bubble`,
    with `score=None` so no score/reasons line renders) but with the wider
    12-bubble carousel cap and browse-oriented copy, since this is a list to
    pick from, not a ranked recommendation."""
    bubbles = [_report_bubble(card) for card in cards[:12]]
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {"type": "flex", "altText": "請選擇想領養的毛孩", "contents": contents}


def _report_bubble(card: MatchReportCard) -> dict:
    _, accent = _REPORT_ACCENT
    title = f"🐾 {card.name}．{card.shelter_number or '無收容編號'}"
    if card.rank is not None:
        title = f"{title}　🎈 第 {card.rank} 名推薦"
    body_contents: list[dict] = [
        _accent_bar(accent),
        {
            "type": "text",
            "text": title,
            "weight": "bold",
            "size": "md",
            "wrap": True,
            "color": _TEXT_COLOR,
            "margin": "md",
        },
    ]
    if card.score is not None:
        body_contents.append(
            {
                "type": "text",
                "text": f"🌟 合拍度 {card.score}%",
                "size": "sm",
                "color": _TEXT_COLOR,
                "margin": "sm",
            }
        )
    if card.reasons:
        reasons_heading = "💡 為什麼推薦給你：" if card.rank is not None else "💡 幾個小發現："
        reasons_body = "\n".join(f"🐾 {reason}" for reason in card.reasons)
        body_contents.append(
            {
                "type": "text",
                "text": f"{reasons_heading}\n{reasons_body}",
                "size": "xs",
                "color": _TEXT_COLOR,
                "wrap": True,
                "margin": "sm",
            }
        )
    if card.selectable:
        body_contents.append(
            _pill_row(
                {
                    "type": "postback",
                    "label": card.select_label,
                    "data": urlencode(
                        {
                            "action": card.select_action,
                            "flow": "adoption",
                            "value": card.animal_id,
                        }
                    ),
                    "displayText": f"選擇{card.name}",
                },
                emoji="🐾",
                text=card.select_label,
                accent=accent,
            )
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
    if card.photo_url:
        bubble["hero"] = {
            "type": "image",
            "url": card.photo_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        }
    return bubble


@dataclass(frozen=True)
class AiSuitabilityCard:
    animal_id: str
    name: str
    shelter_number: str | None
    photo_url: str | None
    score: int
    explanation: str


def build_ai_suitability_card(card: AiSuitabilityCard) -> dict:
    """The async AI-analysis push's headline card — same visual language as
    `_report_bubble` (hero photo, accent bar, score line) but with a full
    explanation paragraph instead of short bullet reasons, since Gemini's
    output is prose, not a list."""
    _, accent = _REPORT_ACCENT
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
                    "text": f"🤖 AI 適配度分析．{card.name}",
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": f"🌟 適配度 {card.score}%",
                    "size": "sm",
                    "color": _TEXT_COLOR,
                    "margin": "sm",
                },
                {
                    "type": "text",
                    "text": card.explanation,
                    "size": "xs",
                    "color": _TEXT_COLOR,
                    "wrap": True,
                    "margin": "sm",
                },
            ],
        },
    }
    if card.photo_url:
        bubble["hero"] = {
            "type": "image",
            "url": card.photo_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        }
    return {
        "type": "flex",
        "altText": f"AI 適配度分析：{card.name} {card.score}%",
        "contents": bubble,
    }


@dataclass(frozen=True)
class QuestionOption:
    code: str
    emoji: str
    label: str


def build_question_card(
    *,
    question_key: str,
    interaction_version: int,
    step: int,
    total: int,
    prompt: str,
    options: list[QuestionOption],
    accent_index: int,
    back_action: dict | None,
) -> dict:
    """One questionnaire question as its own Flex bubble — replaces the
    plain-text + quickReply rendering so the question can carry a header
    badge, a real (server-computed) progress bar, and thick-bordered pill
    options with a leading emoji badge, matching the reference style."""
    header_bg, accent = _PALETTE[accent_index % len(_PALETTE)]
    filled = max(step, 0)
    remaining = max(total - step, 0)
    option_rows = [
        _pill_row(
            {
                "type": "postback",
                "label": option.label[:20],
                "data": urlencode(
                    {
                        "action": "answer",
                        "flow": "adoption",
                        "question": question_key,
                        "version": interaction_version,
                        "value": option.code,
                    }
                ),
                "displayText": option.label,
            },
            emoji=option.emoji,
            text=option.label,
            accent=accent,
            margin="none" if index == 0 else "sm",
        )
        for index, option in enumerate(options)
    ]
    footer: list[dict] = []
    if back_action is not None:
        footer.append(
            {
                "type": "box",
                "layout": "vertical",
                "borderColor": _BORDER_COLOR,
                "borderWidth": "medium",
                "cornerRadius": "lg",
                "paddingAll": "sm",
                "margin": "md",
                "action": back_action,
                "contents": [
                    {
                        "type": "text",
                        "text": "← 上一步",
                        "align": "center",
                        "color": _TEXT_COLOR,
                        "weight": "bold",
                    }
                ],
            }
        )
    return {
        "type": "flex",
        "altText": prompt,
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": header_bg,
                "paddingAll": "md",
                "spacing": "xs",
                "contents": [
                    {
                        "type": "text",
                        "text": f"領養問卷．第 {step} / {total} 題",
                        "size": "xs",
                        "color": _TEXT_COLOR,
                    },
                    {
                        "type": "text",
                        "text": prompt,
                        "size": "md",
                        "weight": "bold",
                        "wrap": True,
                        "color": _TEXT_COLOR,
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "height": "6px",
                        "margin": "sm",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "vertical",
                                "flex": filled,
                                "backgroundColor": accent,
                                "contents": [],
                            },
                            {
                                "type": "box",
                                "layout": "vertical",
                                "flex": remaining,
                                "backgroundColor": _TRACK_COLOR,
                                "contents": [],
                            },
                        ],
                    },
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": _CARD_BG,
                "borderColor": _BORDER_COLOR,
                "borderWidth": "medium",
                "cornerRadius": "lg",
                "paddingAll": "md",
                "spacing": "none",
                "contents": option_rows + footer,
            },
        },
    }


def _summary_row(label: str, value: str) -> dict:
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "sm",
        "contents": [
            {"type": "text", "text": "▪", "size": "xs", "color": _BORDER_COLOR, "flex": 0},
            {
                "type": "text",
                "text": label,
                "size": "xs",
                "color": _TEXT_COLOR,
                "flex": 2,
                "wrap": True,
            },
            {
                "type": "text",
                "text": value,
                "size": "xs",
                "color": _TEXT_COLOR,
                "weight": "bold",
                "flex": 3,
                "wrap": True,
            },
        ],
    }


def build_info_card(
    title: str,
    *,
    accent_index: int,
    body: str | None = None,
    rows: list[tuple[str, str]] | None = None,
    footer_note: str | None = None,
    actions: list[tuple[str, str, dict]] | None = None,
) -> dict:
    """A lightweight Flex bubble for the plain-guidance/confirmation messages
    that used to be a bare text message or a native LINE Buttons Template —
    header badge + optional body text + optional label/value bullet rows
    (`rows`, for the REVIEWING summary) + optional small muted caption
    (`footer_note`) + 0-3 pill-style action buttons (`actions`, as
    `(emoji, label, action_dict)` tuples)."""
    header_bg, accent = _PALETTE[accent_index % len(_PALETTE)]
    body_contents: list[dict] = []
    if body:
        body_contents.append(
            {"type": "text", "text": body, "size": "sm", "color": _TEXT_COLOR, "wrap": True}
        )
    if rows:
        body_contents.append(
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "margin": "sm" if body else "none",
                "contents": [_summary_row(label, value) for label, value in rows],
            }
        )
    if footer_note:
        body_contents.append(
            {
                "type": "text",
                "text": footer_note,
                "size": "xxs",
                "color": "#8a7a6b",
                "wrap": True,
                "margin": "sm" if body_contents else "none",
            }
        )
    for index, (emoji, label, action) in enumerate(actions or []):
        body_contents.append(
            _pill_row(
                action,
                emoji=emoji,
                text=label,
                accent=accent,
                margin="none" if index == 0 and not body_contents else "sm",
            )
        )
    bubble: dict = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": header_bg,
            "paddingAll": "md",
            "cornerRadius": "lg" if not body_contents else "none",
            "contents": [
                {
                    "type": "text",
                    "text": title,
                    "size": "md",
                    "weight": "bold",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                }
            ],
        },
    }
    # A pure navigational nudge (e.g. "請從下方選單選擇想去的地區") has no
    # body/rows/actions at all — omit the body box entirely rather than
    # rendering an empty bordered rectangle under the header (a real bug
    # caught live: a blank cream box was showing up under the header text).
    if body_contents:
        bubble["body"] = {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": _CARD_BG,
            "borderColor": _BORDER_COLOR,
            "borderWidth": "medium",
            "cornerRadius": "lg",
            "paddingAll": "md",
            "spacing": "sm",
            "contents": body_contents,
        }
    return {"type": "flex", "altText": title, "contents": bubble}


def build_animal_confirm_card(
    *,
    name: str,
    shelter_number: str | None,
    photo_url: str | None,
    confirm_action: dict,
    back_action: dict,
    accent_index: int = 0,
) -> dict:
    """The "是這隻毛孩嗎？" confirmation card — photo (if available) as the
    hero image plus confirm/"reselect" pill buttons, replacing the previous
    two-message pattern (a bare image message + a native Buttons Template).
    `back_action` returns to the animal picker (draft.target_animal_id
    cleared) rather than cancelling the whole draft — a full cancel is
    offered separately via quickReply, see the call site."""
    _, accent = _PALETTE[accent_index % len(_PALETTE)]
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
                {
                    "type": "text",
                    "text": f"🐾 {name}．{shelter_number or '無收容編號'}　是這隻毛孩嗎？",
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                },
                _pill_row(confirm_action, emoji="✅", text="沒錯，就是他", accent=accent),
                _pill_row(
                    back_action, emoji="🔁", text="不是，重新選一隻", accent=accent, margin="sm"
                ),
            ],
        },
    }
    if photo_url:
        bubble["hero"] = {
            "type": "image",
            "url": photo_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        }
    return {"type": "flex", "altText": f"確認：{name}", "contents": bubble}
