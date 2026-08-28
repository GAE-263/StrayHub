"""Pure LINE Flex Message JSON builders for the adoption matching flow.

No I/O here — callers fetch data (shelters, animals, photo URLs, match
scores) and pass it in as the dataclasses below; these functions only shape
the Flex JSON. LINE Flex Message boxes support borderWidth/borderColor/
cornerRadius/backgroundColor but NOT boxShadow or custom fonts (text always
renders in the LINE client's system font)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

_BORDER_COLOR = "#716053"
_CARD_BG = "#FAF6EE"
_TEXT_COLOR = "#716053"
_ACCENT_COLOR = "#716053"


@dataclass(frozen=True)
class ShelterCard:
    organization_id: str
    name: str
    service_area: str | None
    adoptable_count: int


def build_shelter_carousel(shelters: list[ShelterCard]) -> dict:
    bubbles = [_shelter_bubble(shelter) for shelter in shelters[:12]]
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {"type": "flex", "altText": "請選擇要領養的收容所", "contents": contents}


def _shelter_bubble(shelter: ShelterCard) -> dict:
    area_line = f"📍 {shelter.service_area or '地區未提供'}．{shelter.adoptable_count} 隻待認養"
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
                    "text": f"🏠 {shelter.name}",
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": _TEXT_COLOR,
                },
                {
                    "type": "text",
                    "text": area_line,
                    "size": "sm",
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
                        "label": "選擇這裡 🐾",
                        "data": urlencode(
                            {
                                "action": "select_organization",
                                "flow": "adoption",
                                "value": shelter.organization_id,
                            }
                        ),
                        "displayText": f"選擇{shelter.name}",
                    },
                },
            ],
        },
    }


@dataclass(frozen=True)
class MatchReportCard:
    animal_id: str
    name: str
    shelter_number: str | None
    photo_url: str | None
    score: float
    reasons: tuple[str, ...] = ()
    rank: int | None = None
    selectable: bool = False


def build_match_report(cards: list[MatchReportCard]) -> dict:
    bubbles = [_report_bubble(card) for card in cards[:3]]
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {"type": "flex", "altText": "適配性報告", "contents": contents}


def _report_bubble(card: MatchReportCard) -> dict:
    title = f"🐾 {card.name}／{card.shelter_number or '無收容編號'}"
    if card.rank is not None:
        title = f"{title}　🎈推薦順位 {card.rank}"
    body_contents: list[dict] = [
        {
            "type": "text",
            "text": title,
            "weight": "bold",
            "size": "md",
            "wrap": True,
            "color": _TEXT_COLOR,
        },
        {
            "type": "text",
            "text": f"🌟 適配度 {round(card.score)} 分",
            "size": "sm",
            "color": _TEXT_COLOR,
            "margin": "sm",
        },
    ]
    if card.reasons:
        body_contents.append(
            {
                "type": "text",
                "text": "\n".join(f"🐾 {reason}" for reason in card.reasons),
                "size": "xs",
                "color": _TEXT_COLOR,
                "wrap": True,
                "margin": "sm",
            }
        )
    if card.selectable:
        body_contents.append(
            {
                "type": "button",
                "style": "primary",
                "color": _ACCENT_COLOR,
                "margin": "md",
                "action": {
                    "type": "postback",
                    "label": "選這隻 🐾",
                    "data": urlencode(
                        {
                            "action": "select_matched_animal",
                            "flow": "adoption",
                            "value": card.animal_id,
                        }
                    ),
                    "displayText": f"選擇{card.name}",
                },
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
    if card.photo_url:
        bubble["hero"] = {
            "type": "image",
            "url": card.photo_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        }
    return bubble
