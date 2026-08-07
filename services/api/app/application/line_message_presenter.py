from __future__ import annotations

from services.api.app.application.effective_observation_service import EffectiveOption


def quick_reply_for_options(options: list[EffectiveOption], *, draft_token: str, step: str) -> dict:
    """Build LINE payloads from CRM option Codes; never trust display labels."""
    return {
        "type": "text",
        "text": "請選擇目前觀察結果",
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": option.display_name[:20],
                        "data": (
                            f"action=answer&draft_token={draft_token}&step={step}"
                            f"&value={option.code}"
                        ),
                        "displayText": option.display_name,
                    },
                }
                for option in options[:6]
            ]
        },
    }
