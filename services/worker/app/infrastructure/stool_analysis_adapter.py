"""Network boundary for the team's stool-analysis API (Cloud Run + Gemini).

串接文件：「便便判讀 API — 串接說明」。這個轉接器只送 subject="stool" 的
照片（由 AIJobRunner 依 image_subject 過濾），一張照片一次呼叫；沒有便便
照片的回報不打 API、直接回空建議，不消耗對方的免費額度。

回傳採 AIAnalysisEnvelope：完整判讀（含 1-7 級分數與照護建議）進
raw_ai_output 供授權人員覆核；正式 Observation 只帶「對應到 CRM 大便選項
的描述性建議」，分數與醫療性建議刻意不進正式欄位——這是 validate_ai_output
既有的治理規則，也符合對方文件「不具醫療診斷效力」的定位。
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from services.api.app.api.errors import DomainError
from services.worker.app.infrastructure.ai_port import AIAnalysisEnvelope, AIRequestVersion


class StoolAnalysisError(RuntimeError):
    """Retryable provider failure; message carries only a safe error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# 對照表以 has_abnormalities 為優先：只要有血絲/黏液/蟲體，不論成形度都
# 對應「有異狀」。分數 1-2（乾硬）與 6-7（糊狀/水瀉）同樣視為異狀，因為
# 志工問卷的四個選項裡沒有「偏硬」。
_SCORE_TO_CODE = {3: "defecation.normal", 4: "defecation.soft", 5: "defecation.soft"}

# 這些錯誤碼重打同一張照片也不會變好，直接標 invalid 終結，不浪費重試額度。
_TERMINAL_ERROR_CODES = {
    "no_image",
    "invalid_image",
    "invalid_api_key",
    "invalid_request",
    "provider_not_configured",
}


def _formal_observation(payload: dict) -> dict:
    """把完整判讀縮成 CRM 允許的描述性建議；分數與建議留在 raw。"""
    if not payload.get("recognized"):
        return {"observations": []}
    score = payload.get("score")
    if payload.get("has_abnormalities"):
        code = "defecation.abnormal"
    else:
        code = _SCORE_TO_CODE.get(score, "defecation.abnormal")
    description = str(payload.get("consistency", "")).strip() or "外觀描述不可用"
    color = str(payload.get("color", "")).strip()
    details = str(payload.get("abnormality_details", "")).strip()
    evidence = "；".join(part for part in (f"顏色：{color}" if color else "", details) if part)
    observation: dict[str, Any] = {"code": code, "description": description}
    if evidence:
        observation["evidence"] = evidence
    return {"observations": [observation]}


class StoolAnalysisAdapter:
    # AIJobRunner 讀這個屬性，只把 subject 相符的照片交給 analyze。
    image_subject = "stool"

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._owns_client = client is None

    async def analyze(
        self,
        *,
        note: str | None,
        image_bytes: list[bytes],
        version: AIRequestVersion,
    ) -> AIAnalysisEnvelope:
        if not image_bytes:
            # 「沒排便」或志工略過拍照的回報：沒有可判讀的內容，不打 API。
            return AIAnalysisEnvelope(
                raw={"skipped": "no_stool_media"}, formal={"observations": []}
            )
        payload = await self._call(image_bytes[0])
        return AIAnalysisEnvelope(raw=payload, formal=_formal_observation(payload))

    async def _call(self, image: bytes) -> dict:
        client = self._client or httpx.AsyncClient()
        try:
            response = await client.post(
                f"{self.endpoint}/v1/analyze/base64",
                json={"image_base64": base64.b64encode(image).decode("ascii")},
                headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise StoolAnalysisError("timeout") from exc
        except httpx.RequestError as exc:
            raise StoolAnalysisError("provider_unavailable") from exc
        finally:
            if self._owns_client:
                await client.aclose()

        if response.status_code != 200:
            code = "provider_http_error"
            try:
                body = response.json()
                candidate = body.get("error", {}).get("code")
                if isinstance(candidate, str) and candidate:
                    code = candidate
            except (ValueError, json.JSONDecodeError, AttributeError):
                pass
            if code in _TERMINAL_ERROR_CODES:
                raise DomainError(code, "便便判讀請求被拒絕，重試同一張照片無效", 422)
            raise StoolAnalysisError(code)

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise StoolAnalysisError("invalid_json") from exc
        if not isinstance(data, dict) or "recognized" not in data:
            raise StoolAnalysisError("invalid_json")
        return data
