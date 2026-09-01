from __future__ import annotations

from dataclasses import dataclass

from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import (
    REQUIRED_ANSWER_KEYS,
    WALK_COMPLETION_CODES,
)


@dataclass(frozen=True)
class EffectiveOption:
    code: str
    display_name: str
    description: str = ""
    requires_note: bool = False
    active: bool = True


class EffectiveObservationService:
    """Validate stable CRM option codes shared by Bot, LIFF and API."""

    def __init__(self, options: dict[str, EffectiveOption] | None = None) -> None:
        self.options = options or {}

    def is_valid(self, code: str, *, category: str | None = None) -> bool:
        if code in WALK_COMPLETION_CODES:
            return True
        if code.startswith("walk_completion."):
            return False
        option = self.options.get(code)
        return (
            option is not None
            and option.active
            and (category is None or code.startswith(f"{category}."))
        )

    def validate_answer(self, field: str, code: str) -> None:
        if field not in REQUIRED_ANSWER_KEYS:
            raise DomainError("invalid_answer_key", "答案欄位不受支援", 422)
        if field == "walk_completion" and code not in WALK_COMPLETION_CODES:
            raise DomainError("invalid_option", "散步完成選項無效", 422)
        if field != "walk_completion" and not self.is_valid(code, category=field):
            raise DomainError("invalid_option", "觀察選項無效或已停用", 422)

    def validate_note_requirement(self, answers: dict[str, str], note: str | None) -> None:
        required_labels = [
            option.display_name
            for code in answers.values()
            if (option := self.options.get(code)) is not None
            and option.requires_note
        ]
        if required_labels and (not note or not note.strip()):
            labels = "、".join(dict.fromkeys(required_labels))
            raise DomainError(
                "observation_note_required", f"選擇「{labels}」時需要補充說明", 422
            )

    def build_quick_reply_options(self, *, category: str) -> list[dict[str, str]]:
        return [
            {"label": option.display_name, "code": option.code}
            for option in self.options.values()
            if option.active and option.code.startswith(f"{category}.")
        ]
