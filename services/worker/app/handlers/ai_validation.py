from __future__ import annotations

import json

from services.api.app.api.errors import DomainError

FORBIDDEN_TERMS = (
    "診斷",
    "疾病",
    "感染",
    "需要就醫",
    "健康正常",
    "沒有外傷",
    "關注分數",
    "危險等級",
)
FORBIDDEN_KEYS = {"animal_id", "score", "level", "formal_status", "medical_diagnosis"}


def validate_ai_output(output: object, *, allowed_codes: set[str]) -> dict:
    if not isinstance(output, dict):
        raise DomainError("invalid_ai_output", "AI 輸出格式無效", 422)
    encoded = json.dumps(output, ensure_ascii=False)
    if any(term in encoded for term in FORBIDDEN_TERMS):
        raise DomainError("forbidden_ai_semantics", "AI 輸出包含禁止的醫療或決策語意", 422)
    if any(key in output for key in FORBIDDEN_KEYS):
        raise DomainError("forbidden_ai_field", "AI 不得產生正式識別或決策欄位", 422)
    observations = output.get("observations", [])
    if not isinstance(observations, list):
        raise DomainError("invalid_ai_output", "AI observations 格式無效", 422)
    for observation in observations:
        if not isinstance(observation, dict) or observation.get("code") not in allowed_codes:
            raise DomainError("unknown_ai_option", "AI 使用了無效觀察選項", 422)
    return output
