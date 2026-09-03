from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AIRequestVersion:
    provider: str
    model_name: str
    model_version: str
    prompt_version: str
    output_schema_version: str
    prompt_template_id: str = "care-observation"


@dataclass(frozen=True)
class AIAnalysisEnvelope:
    """Keep the complete provider payload separate from governed formal output."""

    raw: object
    formal: dict


class AIClientPort(Protocol):
    async def analyze(
        self,
        *,
        note: str | None,
        image_bytes: list[bytes],
        version: AIRequestVersion,
    ) -> object: ...
