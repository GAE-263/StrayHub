"""Network boundary for a versioned descriptive-observation AI provider."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from services.worker.app.infrastructure.ai_port import AIRequestVersion


class AIAdapterError(RuntimeError):
    """Safe provider error whose message contains no request or credential data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AIAdapter:
    def __init__(
        self,
        *,
        endpoint: str | None,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = endpoint
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
    ) -> object:
        if not self.endpoint:
            raise AIAdapterError("provider_not_configured")

        payload = {
            "model": version.model_name,
            "model_version": version.model_version,
            "prompt_template_id": version.prompt_template_id,
            "prompt_version": version.prompt_version,
            "output_schema_version": version.output_schema_version,
            "note": note,
            "images": [base64.b64encode(image).decode("ascii") for image in image_bytes],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        client = self._client or httpx.AsyncClient()
        try:
            response = await client.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise AIAdapterError("timeout") from exc
        except httpx.RequestError as exc:
            raise AIAdapterError("provider_unavailable") from exc
        finally:
            if self._owns_client:
                await client.aclose()

        if response.status_code >= 400:
            raise AIAdapterError("provider_http_error")
        try:
            data: Any = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise AIAdapterError("invalid_json") from exc

        if isinstance(data, dict) and "output" in data:
            return data["output"]
        return data


FormalAIAdapter = AIAdapter
