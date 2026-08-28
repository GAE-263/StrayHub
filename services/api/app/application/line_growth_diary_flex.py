"""Pure LINE Flex Message JSON builder for the growth-diary "which pet"
picker — same visual language as line_adoption_flex.py, kept in its own
module since growth diary is a separate domain flow from adoption matching."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

_BORDER_COLOR = "#716053"
_CARD_BG = "#FAF6EE"
_TEXT_COLOR = "#716053"
_ACCENT_COLOR = "#716053"


@dataclass(frozen=True)
class AdoptedAnimalOption:
    inquiry_id: str
    animal_name: str
    shelter_number: str | None


def build_animal_picker(options: list[AdoptedAnimalOption]) -> dict:
    bubbles = [_bubble(option) for option in options[:12]]
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {"type": "flex", "altText": "請選擇要記錄的毛孩", "contents": contents}


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
                    "text": f"🐾 {option.animal_name}／{option.shelter_number or '無收容編號'}",
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
                        "label": "記錄這隻 🐾",
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
