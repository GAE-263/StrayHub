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
FORBIDDEN_KEYS = {
    "animal_id",
    "score",
    "level",
    "status",
    "formal_status",
    "medical_diagnosis",
    "diagnosis",
    "ranking",
    "rank",
    "sort_order",
    "decision",
}
ALLOWED_OUTPUT_KEYS = {"observations"}
ALLOWED_OBSERVATION_KEYS = {"code", "description", "evidence"}


def validate_ai_output(output: object, *, allowed_codes: set[str]) -> dict:
    if not isinstance(output, dict):
        raise DomainError("invalid_ai_output", "AI 輸出格式無效", 422)
    try:
        encoded = json.dumps(output, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise DomainError("invalid_ai_output", "AI 輸出格式無效", 422) from exc
    if any(term in encoded for term in FORBIDDEN_TERMS):
        raise DomainError("forbidden_ai_semantics", "AI 輸出包含禁止的醫療或決策語意", 422)
    if any(key in FORBIDDEN_KEYS for key in _all_keys(output)):
        raise DomainError("forbidden_ai_field", "AI 不得產生正式識別或決策欄位", 422)
    if set(output) - ALLOWED_OUTPUT_KEYS:
        raise DomainError("invalid_ai_output", "AI 輸出包含未支援欄位", 422)
    observations = output.get("observations", [])
    if not isinstance(observations, list):
        raise DomainError("invalid_ai_output", "AI observations 格式無效", 422)
    for observation in observations:
        if not isinstance(observation, dict):
            raise DomainError("invalid_ai_output", "AI observation 格式無效", 422)
        if set(observation) - ALLOWED_OBSERVATION_KEYS:
            raise DomainError("invalid_ai_output", "AI observation 欄位無效", 422)
        code = observation.get("code")
        if not isinstance(code, str) or code not in allowed_codes:
            raise DomainError("unknown_ai_option", "AI 使用了無效觀察選項", 422)
        for field in ("description", "evidence"):
            if field in observation and not isinstance(observation[field], str):
                raise DomainError("invalid_ai_output", "AI observation 描述格式無效", 422)
    return output


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested in value.values():
            keys.update(_all_keys(nested))
        return keys
    if isinstance(value, list):
        nested_keys: set[str] = set()
        for nested in value:
            nested_keys.update(_all_keys(nested))
        return nested_keys
    return set()
