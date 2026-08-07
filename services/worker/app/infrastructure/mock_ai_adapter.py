from __future__ import annotations

from services.worker.app.infrastructure.ai_port import AIRequestVersion


class MockAIAdapter:
    def __init__(self, *, result: dict | None = None, error: Exception | None = None) -> None:
        self.result = result or {"observations": []}
        self.error = error
        self.requests: list[AIRequestVersion] = []

    async def analyze(
        self,
        *,
        note: str | None,
        image_bytes: list[bytes],
        version: AIRequestVersion,
    ) -> dict:
        self.requests.append(version)
        if self.error:
            raise self.error
        return self.result
