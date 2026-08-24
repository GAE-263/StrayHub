"""Draft Flex bubbles in the block-sticker style, for evaluation only.

Deliberately standalone: this imports nothing from the running presenter and
nothing imports it, so the proposal can be judged without touching production
code. Run it to emit JSON for the LINE Flex Message Simulator.

    python flex_style_draft.py <output_dir>

What the style asks for versus what Flex can actually render:

    cream ground, chocolate text      -> yes
    3-6px solid borders               -> yes, borderWidth/borderColor
    24px corner radius                -> yes, cornerRadius
    emoji accents                     -> yes, unicode renders in colour
    4px 4px 0 0 offset shadow         -> NO, Flex has no shadow of any kind
    Fredoka via Google Fonts          -> NO, messages use the reader's system font

The missing depth is compensated with heavier borders and saturated colour
blocks, which is the closest Flex gets to the sticker feel.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CREAM = "#FAF6EE"
SURFACE = "#FFFCF3"
INK = "#716053"
INK_SOFT = "#9C8B7D"
LEAF = "#A8C69F"
PEACH = "#F2B8A2"
BUTTER = "#F6D77A"
SKY = "#A9C9DB"
TRACK = "#E4DACA"

RADIUS = "24px"
RADIUS_SM = "16px"
BORDER = "4px"
BORDER_THICK = "6px"

TOKEN = "sample-draft-token"


def choice(label: str, data: str, glyph: str, *, fill: str = CREAM) -> dict:
    """A tappable option card: thick border, big radius, emoji lead."""
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "md",
        "backgroundColor": fill,
        "cornerRadius": RADIUS_SM,
        "borderWidth": BORDER,
        "borderColor": INK,
        "paddingAll": "14px",
        "action": {"type": "postback", "label": label[:20], "data": data, "displayText": label},
        "contents": [
            {"type": "text", "text": glyph, "size": "md", "flex": 0, "gravity": "center"},
            {
                "type": "text",
                "text": label,
                "color": INK,
                "size": "md",
                "weight": "bold",
                "wrap": True,
                "gravity": "center",
            },
        ],
    }


def header(glyph: str, caption: str, title: str, fill: str, progress: dict | None = None) -> dict:
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
                        {"type": "text", "text": caption, "size": "xs", "color": INK, "wrap": True},
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
        "backgroundColor": fill,
        "paddingAll": "18px",
        "spacing": "md",
        "contents": contents,
    }


def progress_bar(position: int, total: int) -> dict:
    percent = max(6, min(100, round(position * 100 / max(1, total))))
    return {
        "type": "box",
        "layout": "horizontal",
        "height": "14px",
        "backgroundColor": TRACK,
        "cornerRadius": "999px",
        "borderWidth": "3px",
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


def hint(text: str) -> dict:
    return {"type": "text", "text": text, "size": "xxs", "color": INK_SOFT, "align": "center"}


def bubble(head: dict, body: dict, foot: dict | None = None) -> dict:
    out = {
        "type": "bubble",
        "size": "mega",
        "header": head,
        "body": body,
        "styles": {"header": {"separator": True, "separatorColor": INK}},
    }
    if foot is not None:
        out["footer"] = foot
    return out


def body_box(contents: list[dict], *, fill: str = SURFACE) -> dict:
    return {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": fill,
        "paddingAll": "16px",
        "spacing": "md",
        "contents": contents,
    }


def question(title, glyph, options, position, total, fill=BUTTER) -> dict:
    return {
        "type": "flex",
        "altText": f"{glyph} {title}（第 {position} / {total} 題）",
        "contents": bubble(
            header(
                glyph,
                f"照護回報 · 第 {position} / {total} 題",
                title,
                fill,
                progress_bar(position, total),
            ),
            body_box(
                [
                    choice(
                        label,
                        f"action=answer&draft_token={TOKEN}&step={title}&value={code}",
                        icon,
                    )
                    for code, label, icon in options
                ]
            ),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "paddingAll": "12px",
                "spacing": "sm",
                "contents": [
                    choice("上一步", f"action=back&draft_token={TOKEN}", "←", fill=SURFACE),
                    hint("點錯了也沒關係，可以退回上一題 🍃"),
                ],
            },
        ),
    }


def prompt(title, glyph, caption, text, choices, fill) -> dict:
    return {
        "type": "flex",
        "altText": f"{glyph} {title}",
        "contents": bubble(
            header(glyph, caption, title, fill),
            body_box(
                [{"type": "text", "text": text, "color": INK_SOFT, "size": "sm", "wrap": True}]
                + [choice(label, data, icon) for label, data, icon in choices]
            ),
        ),
    }


def summary(rows, note, choices, animal) -> dict:
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
        row_contents += [
            {"type": "separator", "color": TRACK, "margin": "md"},
            {"type": "text", "text": "📝 今天的心得", "size": "sm", "color": INK_SOFT},
            {"type": "text", "text": note, "size": "sm", "color": INK, "wrap": True},
        ]
    return {
        "type": "flex",
        "altText": "📋 回報摘要，確認後即可送出",
        "contents": bubble(
            header("📋", f"{animal} · 送出前還可以修改", "回報摘要", PEACH),
            body_box(row_contents),
            {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": CREAM,
                "paddingAll": "14px",
                "spacing": "sm",
                "contents": [
                    choice(label, data, icon, fill=BUTTER if i == 0 else SURFACE)
                    for i, (label, data, icon) in enumerate(choices)
                ],
            },
        ),
    }


def celebration(animal: str) -> dict:
    return {
        "type": "flex",
        "altText": "🎉 回報已保存，辛苦了！",
        "contents": bubble(
            header("🎉", "辛苦了，謝謝你", "回報完成", LEAF),
            body_box(
                [
                    {
                        "type": "text",
                        "text": f"陪 {animal} 的紀錄已經收好了 🌟",
                        "color": INK,
                        "size": "md",
                        "weight": "bold",
                        "wrap": True,
                        "align": "center",
                    },
                    {
                        "type": "text",
                        "text": "AI 分析會在背景進行，不影響這筆紀錄。",
                        "color": INK_SOFT,
                        "size": "xs",
                        "wrap": True,
                        "align": "center",
                    },
                    hint("下次要回報，再按一次選單就好 🐾"),
                ]
            ),
        ),
    }


SAMPLES = {
    "01-question-feeding": question(
        "進食",
        "🍚",
        [
            ("feeding.normal", "正常", "🥣"),
            ("feeding.less", "較少", "🍽️"),
            ("feeding.almost_none", "幾乎沒吃", "😶"),
            ("feeding.not_provided", "未提供", "🚫"),
            ("feeding.not_observed", "未觀察到", "👀"),
            ("feeding.uncertain", "不確定", "❓"),
        ],
        3,
        13,
    ),
    "02-prompt-photo": prompt(
        "拍一張今天的牠",
        "📸",
        "照護回報 · 選填",
        "直接在聊天室傳照片就可以了，想傳幾張都行。沒拍到也沒關係。",
        [
            ("略過照片", f"action=skip_media&draft_token={TOKEN}", "⏭"),
            ("上一步", f"action=back&draft_token={TOKEN}", "←"),
        ],
        SKY,
    ),
    "03-summary": summary(
        [
            ("🧺", "照護完成", "已完成"),
            ("🚶", "散步完成", "已完成"),
            ("🍚", "進食", "正常"),
            ("💧", "飲水", "有喝水"),
            ("⚡", "活動", "較高"),
            ("💩", "排便", "形狀不同、顏色偏深"),
            ("🦴", "護食", "未觀察到"),
            ("🔍", "外觀／特殊狀態", "局部搔抓、毛量偏少"),
        ],
        "今天散步時精神很好，一直想往草叢跑。",
        [
            ("送出回報", f"action=submit&draft_token={TOKEN}", "✅"),
            ("再改一下", f"action=back&draft_token={TOKEN}", "✏️"),
            ("換一隻", f"action=reselect_animal&draft_token={TOKEN}", "🔄"),
        ],
        "小黑",
    ),
    "04-celebration": celebration("小黑"),
}


def main() -> None:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, message in SAMPLES.items():
        path = out_dir / f"{name}.json"
        path.write_text(
            json.dumps(message["contents"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        size = len(json.dumps(message, ensure_ascii=False).encode())
        flag = "  OVER 10KB" if size > 10240 else ""
        print(f"{path.name:26s} {size:6d} bytes{flag}")


if __name__ == "__main__":
    main()
