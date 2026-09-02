"""Network boundary for the stool-photo analysis provider."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from services.api.app.api.errors import DomainError
from services.worker.app.infrastructure.ai_port import AIAnalysisEnvelope, AIRequestVersion


class StoolAnalysisError(RuntimeError):
    """Retryable provider failure whose text contains only a safe error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_SCORE_TO_CODE = {3: "defecation.normal", 4: "defecation.soft", 5: "defecation.soft"}
_TERMINAL_ERROR_CODES = {
    "no_image",
    "invalid_image",
    "invalid_api_key",
    "invalid_request",
    "provider_not_configured",
}


def _formal_observation(payload: dict) -> dict:
    if not payload["recognized"]:
        return {"observations": []}
    score = payload["score"]
    code = (
        "defecation.abnormal"
        if payload["has_abnormalities"]
        else _SCORE_TO_CODE.get(score, "defecation.abnormal")
    )
    description = payload["consistency"].strip() or "外觀描述不可用"
    color = payload["color"].strip()
    details = payload["abnormality_details"].strip()
    evidence = "；".join(part for part in (f"顏色：{color}" if color else "", details) if part)
    observation: dict[str, Any] = {"code": code, "description": description}
    if evidence:
        observation["evidence"] = evidence
    return {"observations": [observation]}


def _validated_payload(data: object) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("recognized"), bool):
        raise StoolAnalysisError("invalid_json")
    if not data["recognized"]:
        return data
    if (
        not isinstance(data.get("score"), int)
        or isinstance(data.get("score"), bool)
        or not 1 <= data["score"] <= 7
        or not isinstance(data.get("has_abnormalities"), bool)
        or any(
            not isinstance(data.get(field), str)
            for field in ("consistency", "color", "abnormality_details")
        )
    ):
        raise StoolAnalysisError("invalid_json")
    return data


class StoolAnalysisAdapter:
    image_subject = "stool"

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not endpoint.strip() or not api_key:
            raise ValueError("stool analysis provider configuration is incomplete")
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

        if response.status_code >= 400:
            code = f"provider_http_{response.status_code}"
            try:
                body = response.json()
                candidate = body.get("error", {}).get("code")
                if isinstance(candidate, str) and candidate:
                    code = candidate
            except (ValueError, json.JSONDecodeError, AttributeError):
                pass
            if code in _TERMINAL_ERROR_CODES or (
                400 <= response.status_code < 500 and response.status_code not in {408, 429}
            ):
                raise DomainError(code, "便便判讀請求被拒絕，重試同一張照片無效", 422)
            raise StoolAnalysisError(code)

        try:
            return _validated_payload(response.json())
        except (ValueError, json.JSONDecodeError) as exc:
            raise StoolAnalysisError("invalid_json") from exc
