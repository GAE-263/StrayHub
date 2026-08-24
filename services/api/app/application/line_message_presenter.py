from __future__ import annotations

from services.api.app.application.effective_observation_service import EffectiveOption

# Presentation tokens only. Business vocabulary — option codes, category names,
# answer labels — must always arrive from the CRM, never from this module.
INK = "#1F3D36"
INK_SOFT = "#5C7168"
CREAM = "#FDF7E6"
CREAM_DEEP = "#F4E9CE"
LEAF = "#5BA85F"
GREEN = "#2E8B6B"
GREEN_DEEP = "#1C6350"
GREEN_PALE = "#CDECDC"
WOOD = "#C8944A"
WOOD_DEEP = "#A5762F"
SKY = "#79B8D1"
BORDER = "#DCE9E0"
WHITE = "#FFFFFF"
PROGRESS = "#F7D774"
PROGRESS_TRACK = "#17513F"

_LABEL_LIMIT = 20
_ROUND = "18px"
_ROUND_SM = "12px"


def _gradient(start: str, end: str, angle: str = "160deg") -> dict:
    return {"type": "linearGradient", "angle": angle, "startColor": start, "endColor": end}


def _answer_action(option: EffectiveOption, *, draft_token: str, step: str) -> dict:
    return {
        "type": "postback",
        "label": option.display_name[:_LABEL_LIMIT],
        "data": f"action=answer&draft_token={draft_token}&step={step}&value={option.code}",
        "displayText": option.display_name,
    }


def _choice_box(label: str, action: dict, *, tint: str = WHITE, glyph: str = "") -> dict:
    """A tappable card. Boxes are used instead of buttons so the palette applies."""
    row: list[dict] = []
    if glyph:
        row.append({"type": "text", "text": glyph, "size": "md", "flex": 0})
    row.append(
        {
            "type": "text",
            "text": label,
            "color": INK,
            "size": "md",
            "weight": "bold",
            "align": "center" if not glyph else "start",
            "wrap": True,
            "gravity": "center",
        }
    )
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "md",
        "backgroundColor": tint,
        "cornerRadius": _ROUND,
        "borderWidth": "2px",
        "borderColor": BORDER,
        "paddingAll": "15px",
        "action": action,
        "contents": row,
    }


def _progress_bar(position: int, total: int) -> dict:
    percent = max(6, min(100, round(position * 100 / max(1, total))))
    return {
        "type": "box",
        "layout": "horizontal",
        "height": "12px",
        "backgroundColor": PROGRESS_TRACK,
        "cornerRadius": "6px",
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "width": f"{percent}%",
                "backgroundColor": PROGRESS,
                "cornerRadius": "6px",
                "contents": [{"type": "filler"}],
            }
        ],
    }


def _header(
    title: str,
    caption: str,
    *,
    glyph: str = "🌿",
    start: str = LEAF,
    end: str = GREEN_DEEP,
    progress: dict | None = None,
) -> dict:
    contents: list[dict] = [
        {
            "type": "box",
            "layout": "horizontal",
            "spacing": "md",
            "contents": [
                {"type": "text", "text": glyph, "size": "xxl", "flex": 0, "gravity": "center"},
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": caption, "size": "xs", "color": GREEN_PALE},
                        {
                            "type": "text",
                            "text": title,
                            "size": "xl",
                            "weight": "bold",
                            "color": CREAM,
                            "wrap": True,
                        },
                    ],
                },
            ],
        }
    ]
    if progress is not None:
        contents.append(progress)
    return {
        "type": "box",
        "layout": "vertical",
        "background": _gradient(start, end),
        "paddingAll": "20px",
        "spacing": "md",
        "contents": contents,
    }


def _hint(text: str) -> dict:
    return {"type": "text", "text": text, "size": "xxs", "color": INK_SOFT, "align": "center"}


def _back_footer(draft_token: str, *, hint: str = "點錯了也沒關係，可以退回上一題 🍃") -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": CREAM_DEEP,
        "paddingAll": "12px",
        "spacing": "sm",
        "contents": [
            {
                "type": "button",
                "style": "link",
                "height": "sm",
                "color": GREEN_DEEP,
                "action": {
                    "type": "postback",
                    "label": "← 上一步",
                    "data": f"action=back&draft_token={draft_token}",
                    "displayText": "上一步",
                },
            },
            _hint(hint),
        ],
    }


def _bubble(header: dict, body: dict, footer: dict | None = None) -> dict:
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": header,
        "body": body,
        "styles": {
            "header": {"separator": False},
            "body": {"separator": False},
        },
    }
    if footer is not None:
        bubble["footer"] = footer
    return bubble


def question_bubble(
    options: list[EffectiveOption],
    *,
    draft_token: str,
    step: str,
    title: str,
    position: int,
    total: int,
    glyph: str = "🐾",
) -> dict:
    """One question per card: what is being asked, how far along, every option."""
    if options:
        body_contents = [
            _choice_box(
                option.display_name,
                _answer_action(option, draft_token=draft_token, step=step),
            )
            for option in options
        ]
        body_contents.append(
            _choice_box(
                "今天沒觀察到這項",
                {
                    "type": "postback",
                    "label": "沒觀察到這項",
                    "data": f"action=skip_question&draft_token={draft_token}",
                    "displayText": "今天沒觀察到這項",
                },
                tint=CREAM_DEEP,
                glyph="👀",
            )
        )
    else:
        # An empty vocabulary is a configuration fault; say so instead of
        # presenting a card with nothing to tap.
        body_contents = [
            {
                "type": "text",
                "text": "這個項目目前沒有可選的觀察選項，請聯絡工作人員 🙇",
                "color": INK,
                "size": "sm",
                "wrap": True,
            }
        ]
    return {
        "type": "flex",
        "altText": f"{glyph} {title}（第 {position} / {total} 題）",
        "contents": _bubble(
            _header(
                title,
                f"照護回報 · 第 {position} / {total} 題",
                glyph=glyph,
                progress=_progress_bar(position, total),
            ),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "paddingAll": "16px",
                "spacing": "sm",
                "contents": body_contents,
            },
            _back_footer(draft_token),
        ),
    }


def prompt_bubble(
    *,
    title: str,
    caption: str,
    body_text: str,
    choices: list[tuple[str, str, str]],
    glyph: str = "🌸",
    start: str = SKY,
    end: str = "#3E7E99",
) -> dict:
    """A step that asks for something other than a vocabulary answer."""
    return {
        "type": "flex",
        "altText": f"{glyph} {title}",
        "contents": _bubble(
            _header(title, caption, glyph=glyph, start=start, end=end),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "paddingAll": "16px",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": body_text,
                        "color": INK_SOFT,
                        "size": "sm",
                        "wrap": True,
                    },
                    {"type": "separator", "color": BORDER, "margin": "md"},
                ]
                + [
                    _choice_box(
                        label,
                        {
                            "type": "postback",
                            "label": label[:_LABEL_LIMIT],
                            "data": data,
                            "displayText": label,
                        },
                        glyph=icon,
                    )
                    for label, data, icon in choices
                ],
            },
        ),
    }


def _animal_status_row(label: str, data: str, *, cared_caption: str, cared: bool) -> dict:
    """One animal in the daily overview: who it is, and whether today is done."""
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "md",
        "backgroundColor": GREEN_PALE if cared else WHITE,
        "cornerRadius": _ROUND,
        "borderWidth": "2px",
        "borderColor": BORDER,
        "paddingAll": "14px",
        "action": {
            "type": "postback",
            "label": label[:_LABEL_LIMIT],
            "data": data,
            "displayText": label,
        },
        "contents": [
            {
                "type": "text",
                "text": "✅" if cared else "⬜",
                "size": "md",
                "flex": 0,
                "gravity": "center",
            },
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "contents": [
                    {
                        "type": "text",
                        "text": label,
                        "color": INK,
                        "size": "md",
                        "weight": "bold",
                        "wrap": True,
                    },
                    {"type": "text", "text": cared_caption, "color": INK_SOFT, "size": "xs"},
                ],
            },
        ],
    }


def daily_care_bubble(
    rows: list[tuple[str, str, str, bool]],
    *,
    done: int,
    total: int,
    shown_through: int,
    more_data: str | None = None,
) -> dict:
    """Today's animals and what still needs doing.

    ``rows`` are (label, postback data, caption, already cared for). The counts
    describe the whole day, not the page: a volunteer who only ever sees one
    page must still be able to tell that more animals exist.
    """
    body_contents: list[dict] = [
        _animal_status_row(label, data, cared_caption=caption, cared=cared)
        for label, data, caption, cared in rows
    ]
    if more_data is not None:
        body_contents.append(
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM_DEEP,
                "cornerRadius": _ROUND,
                "paddingAll": "14px",
                "action": {
                    "type": "postback",
                    "label": "顯示更多",
                    "data": more_data,
                    "displayText": "顯示更多",
                },
                "contents": [
                    {
                        "type": "text",
                        "text": f"顯示更多（還有 {total - shown_through} 隻）",
                        "color": GREEN_DEEP,
                        "size": "sm",
                        "weight": "bold",
                        "align": "center",
                    }
                ],
            }
        )
    return {
        "type": "flex",
        "altText": f"🐾 今日照護毛孩（已回報 {done} / {total}）",
        "contents": _bubble(
            _header(
                "今日照護毛孩",
                f"共 {total} 隻 · 已回報 {done} 隻",
                glyph="🐾",
                progress=_progress_bar(done, total),
            ),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "paddingAll": "16px",
                "spacing": "sm",
                "contents": body_contents,
            },
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM_DEEP,
                "paddingAll": "12px",
                "contents": [_hint("點一下毛孩就可以開始回報 🍃")],
            },
        ),
    }


def summary_bubble(
    rows: list[tuple[str, str, str]],
    *,
    note: str | None,
    choices: list[tuple[str, str, str]],
    animal_name: str = "",
    story: str | None = None,
) -> dict:
    """The pre-submit review card; rows are already display names from the CRM."""
    row_contents: list[dict] = []
    for glyph, label, value in rows:
        row_contents.append(
            {
                "type": "box",
                "layout": "baseline",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": glyph, "size": "sm", "flex": 0},
                    {"type": "text", "text": label, "size": "sm", "color": INK_SOFT, "flex": 4},
                    {
                        "type": "text",
                        "text": value,
                        "size": "sm",
                        "color": INK,
                        "weight": "bold",
                        "flex": 6,
                        "wrap": True,
                    },
                ],
            }
        )
    if note:
        row_contents.extend(
            [
                {"type": "separator", "color": BORDER, "margin": "md"},
                {"type": "text", "text": "📝 今天的心得", "size": "sm", "color": INK_SOFT},
                {"type": "text", "text": note, "size": "sm", "color": INK, "wrap": True},
            ]
        )
    if story:
        row_contents.extend(
            [
                {"type": "separator", "color": BORDER, "margin": "md"},
                {"type": "text", "text": "✨ 小故事", "size": "sm", "color": INK_SOFT},
                {"type": "text", "text": story, "size": "sm", "color": INK, "wrap": True},
            ]
        )
    caption = f"{animal_name} · 送出前還可以修改" if animal_name else "送出前還可以修改"
    return {
        "type": "flex",
        "altText": "📋 回報摘要，確認後即可送出",
        "contents": _bubble(
            _header("回報摘要", caption, glyph="📋", start=WOOD, end=WOOD_DEEP),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "paddingAll": "16px",
                "spacing": "sm",
                "contents": row_contents,
            },
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM_DEEP,
                "paddingAll": "14px",
                "spacing": "sm",
                "contents": [
                    _choice_box(
                        label,
                        {
                            "type": "postback",
                            "label": label[:_LABEL_LIMIT],
                            "data": data,
                            "displayText": label,
                        },
                        tint=PROGRESS if index == 0 else WHITE,
                        glyph=icon,
                    )
                    for index, (label, data, icon) in enumerate(choices)
                ],
            },
        ),
    }


def celebration_bubble(*, animal_name: str = "") -> dict:
    """Shown once the report is saved, so submitting feels like an ending."""
    who = f"陪 {animal_name} 的紀錄已經收好了" if animal_name else "今天的紀錄已經收好了"
    return {
        "type": "flex",
        "altText": "🎉 回報已保存，辛苦了！",
        "contents": _bubble(
            _header("回報完成", "辛苦了，謝謝你 💚", glyph="🎉", start=LEAF, end=GREEN),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "paddingAll": "18px",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": who,
                        "color": INK,
                        "size": "md",
                        "weight": "bold",
                        "wrap": True,
                        "align": "center",
                    },
                    {
                        "type": "text",
                        "text": "AI 分析會在背景進行，不會影響這筆紀錄。",
                        "color": INK_SOFT,
                        "size": "xs",
                        "wrap": True,
                        "align": "center",
                    },
                    {"type": "separator", "color": BORDER, "margin": "md"},
                    _hint("下次要回報，再按一次選單就好 🌿"),
                ],
            },
        ),
    }
