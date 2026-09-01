from __future__ import annotations

from services.api.app.application.effective_observation_service import EffectiveOption

# Presentation tokens only. Business vocabulary — option codes, category names,
# answer labels — must always arrive from the CRM, never from this module.
#
# Palette matches the "block sticker" mockup approved in style-preview/v2
# (interactive.html's CSS custom properties): cream paper, ink-brown text and
# borders, pastel tone cards. LINE Flex has no box-shadow and cannot load a
# custom font, so the mockup's hard offset shadow and Fredoka typeface have no
# Flex equivalent — accepted trade-off, confirmed during the mockup review.
INK = "#716053"
# Secondary ink still has to be *read*: labels, captions and every body line of
# a choice-less prompt card are drawn in it. #9C8B7D scored 3.2:1 on SURFACE —
# below AA for text this small — so it is darkened to 4.95:1 here. Captions
# that sit on a saturated tone use INK instead (see _header); the pastel tones
# cap out around 3.2:1 even for INK, which is a property of the approved
# palette rather than something a text colour can fix.
INK_SOFT = "#7E6B59"
CREAM = "#FAF6EE"
SURFACE = "#FFFCF3"
TRACK = "#E4DACA"
LEAF = "#A8C69F"
BUTTER = "#F6D77A"
PEACH = "#F2B8A2"
SKY = "#A9C9DB"
LILAC = "#C9B6D9"
WHITE = "#FFFFFF"

# Kept as aliases so call sites that ask for a "warning/required" tone read
# naturally; both now point at the block-sticker palette, not the old greens.
WOOD = PEACH
WOOD_DEEP = PEACH

_LABEL_LIMIT = 20
_ROUND = "24px"
_ROUND_SM = "16px"
_BORDER = "3px"
_BORDER_THICK = "4px"


def _answer_action(option: EffectiveOption, *, draft_token: str, step: str) -> dict:
    return {
        "type": "postback",
        "label": option.display_name[:_LABEL_LIMIT],
        "data": f"action=answer&draft_token={draft_token}&step={step}&value={option.code}",
        "displayText": option.display_name,
    }


def _choice_box(label: str, action: dict, *, tint: str = SURFACE, glyph: str = "") -> dict:
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
        "cornerRadius": _ROUND_SM,
        "borderWidth": _BORDER,
        "borderColor": INK,
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
        "backgroundColor": TRACK,
        "cornerRadius": "999px",
        "borderWidth": "2px",
        "borderColor": INK,
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "width": f"{percent}%",
                "backgroundColor": BUTTER,
                "cornerRadius": "999px",
                "contents": [{"type": "filler"}],
            }
        ],
    }


def _header(
    title: str,
    caption: str,
    *,
    glyph: str = "🐾",
    tone: str = BUTTER,
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
                        {"type": "text", "text": caption, "size": "xs", "color": INK},
                        {
                            "type": "text",
                            "text": title,
                            "size": "xl",
                            "weight": "bold",
                            "color": INK,
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
        "backgroundColor": tone,
        "cornerRadius": _ROUND,
        "borderWidth": _BORDER_THICK,
        "borderColor": INK,
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
        "backgroundColor": CREAM,
        "cornerRadius": _ROUND,
        "borderWidth": _BORDER_THICK,
        "borderColor": INK,
        "paddingAll": "12px",
        "spacing": "sm",
        "contents": [
            {
                "type": "button",
                "style": "link",
                "height": "sm",
                "color": INK,
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


def _body_box(contents: list[dict]) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": SURFACE,
        "cornerRadius": _ROUND,
        "borderWidth": _BORDER_THICK,
        "borderColor": INK,
        "paddingAll": "16px",
        "spacing": "sm",
        "contents": contents,
    }


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
                tint=CREAM,
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
                f"散步回報 · 第 {position} / {total} 題",
                glyph=glyph,
                tone=BUTTER,
                progress=_progress_bar(position, total),
            ),
            _body_box(body_contents),
            _back_footer(draft_token),
        ),
    }


def _info_row(glyph: str, label: str, value: str) -> dict:
    """A labelled fact on its own line — large enough and high-contrast enough
    to actually read at a glance, unlike cramming it into the header caption."""
    return {
        "type": "box",
        # Not "baseline": that layout renders every child on one line and
        # ellipsises the overflow, so `wrap` below is ignored and a long area
        # name is cut off instead of continuing on the next line.
        "layout": "horizontal",
        "spacing": "sm",
        "contents": [
            {"type": "text", "text": glyph, "size": "sm", "flex": 0},
            {"type": "text", "text": label, "size": "sm", "color": INK_SOFT, "flex": 3},
            {
                "type": "text",
                "text": value,
                "size": "md",
                "color": INK,
                "weight": "bold",
                "flex": 7,
                "wrap": True,
            },
        ],
    }


def animal_confirmation_bubble(
    *,
    animal_name: str,
    shelter_number: str,
    area_label: str,
    confirm_data: str,
    organization_name: str = "",
    photo_url: str | None = None,
    reselect_data: str = "action=find_dog",
) -> dict:
    """Is-this-the-right-animal card, replacing the old plain-text + Template
    Message pair so every step in the flow reads as the same visual system.

    Shelter number and area live as their own body rows, not squeezed into the
    small header caption — a volunteer scanning quickly must be able to read
    both without zooming in.
    """
    body_rows = [
        _info_row("🏷", "收容編號", shelter_number),
        _info_row("📍", "所在區域", area_label),
    ]
    if organization_name:
        body_rows.append(_info_row("🏠", "目前收容所", organization_name))
    body_rows.extend(
        [
            {"type": "separator", "color": TRACK, "margin": "md"},
            _choice_box(
                "確認是這隻",
                {
                    "type": "postback",
                    "label": "確認是這隻",
                    "data": confirm_data,
                    "displayText": "確認是這隻",
                },
                tint=SURFACE,
                glyph="✅",
            ),
            _choice_box(
                "重新選擇",
                {
                    "type": "postback",
                    "label": "重新選擇",
                    "data": reselect_data,
                    "displayText": "重新選擇",
                },
                tint=CREAM,
                glyph="🔄",
            ),
        ]
    )
    bubble = _bubble(
        _header(f"是 {animal_name} 嗎？", "散步回報 · 請確認動物", glyph="🐶", tone=BUTTER),
        _body_box(body_rows),
    )
    if photo_url:
        bubble["hero"] = {
            "type": "image",
            "url": photo_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        }
    return {
        "type": "flex",
        "altText": f"🐶 是 {animal_name} 嗎？",
        "contents": bubble,
    }


def prompt_bubble(
    *,
    title: str,
    caption: str,
    body_text: str,
    choices: list[tuple[str, str, str]],
    glyph: str = "🌸",
    tone: str = SKY,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """A step that asks for something other than a vocabulary answer.

    ``start``/``end`` are accepted and ignored — older call sites passed a
    gradient pair before Flex headers switched to a flat tone; ``start`` maps
    onto ``tone`` for one release so nothing breaks mid-rollout.
    """
    resolved_tone = start or tone
    return {
        "type": "flex",
        "altText": f"{glyph} {title}",
        "contents": _bubble(
            _header(title, caption, glyph=glyph, tone=resolved_tone),
            _body_box(
                [
                    {
                        "type": "text",
                        "text": body_text,
                        "color": INK_SOFT,
                        "size": "sm",
                        "wrap": True,
                    },
                ]
                # A separator only earns its place when something follows it;
                # choice-less cards would otherwise end on a rule and nothing.
                + ([{"type": "separator", "color": TRACK, "margin": "md"}] if choices else [])
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
                ]
            ),
        ),
    }


def _animal_status_row(label: str, data: str, *, cared_caption: str, cared: bool) -> dict:
    """One animal in the daily overview: who it is, and whether today is done."""
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "md",
        "backgroundColor": LEAF if cared else SURFACE,
        "cornerRadius": _ROUND_SM,
        "borderWidth": _BORDER,
        "borderColor": INK,
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
                    {"type": "text", "text": cared_caption, "color": INK, "size": "xs"},
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
    body_contents: list[dict] = []
    current_section: bool | None = None
    for label, data, caption, cared in rows:
        if cared != current_section:
            body_contents.append(
                {
                    "type": "text",
                    "text": "今日已回報" if cared else "尚未回報",
                    "size": "sm",
                    "weight": "bold",
                    "color": INK,
                    "margin": "md" if current_section is not None else "none",
                }
            )
            current_section = cared
        body_contents.append(
            _animal_status_row(label, data, cared_caption=caption, cared=cared)
        )
    if more_data is not None:
        body_contents.append(
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "cornerRadius": _ROUND_SM,
                "borderWidth": _BORDER,
                "borderColor": INK,
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
                        "color": INK,
                        "size": "sm",
                        "weight": "bold",
                        "align": "center",
                    }
                ],
            }
        )
    return {
        "type": "flex",
        "altText": f"🐾 今日散步名單（已回報 {done} / {total}）",
        "contents": _bubble(
            _header(
                "今日散步名單",
                f"共 {total} 隻 · 已回報 {done} 隻",
                glyph="🐾",
                tone=LEAF,
                progress=_progress_bar(done, total),
            ),
            _body_box(body_contents),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "cornerRadius": _ROUND,
                "borderWidth": _BORDER_THICK,
                "borderColor": INK,
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
                # See _info_row: "baseline" would truncate a long answer label
                # rather than wrap it, and the summary is the last chance to
                # notice a wrong answer before submitting.
                "layout": "horizontal",
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
                {"type": "separator", "color": TRACK, "margin": "md"},
                {"type": "text", "text": "📝 健康補充", "size": "sm", "color": INK_SOFT},
                {"type": "text", "text": note, "size": "sm", "color": INK, "wrap": True},
            ]
        )
    if story:
        row_contents.extend(
            [
                {"type": "separator", "color": TRACK, "margin": "md"},
                {"type": "text", "text": "✨ 小故事", "size": "sm", "color": INK_SOFT},
                {"type": "text", "text": story, "size": "sm", "color": INK, "wrap": True},
            ]
        )
    caption = f"{animal_name} · 送出前還可以修改" if animal_name else "送出前還可以修改"
    return {
        "type": "flex",
        "altText": "📋 回報摘要，確認後即可送出",
        "contents": _bubble(
            _header("回報摘要", caption, glyph="📋", tone=PEACH),
            _body_box(row_contents),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "cornerRadius": _ROUND,
                "borderWidth": _BORDER_THICK,
                "borderColor": INK,
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
                        tint=BUTTER if index == 0 else SURFACE,
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
            _header("回報完成", "辛苦了，謝謝你 💚", glyph="🎉", tone=LEAF),
            _body_box(
                [
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
                    {"type": "separator", "color": TRACK, "margin": "md"},
                    _hint("下次要回報，再按一次選單就好 🌿"),
                ]
            ),
        ),
    }
