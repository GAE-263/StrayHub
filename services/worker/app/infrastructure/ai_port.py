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
    """Provider payload split from the formal suggestion built out of it.

    validate_ai_output 刻意禁止 score/評估/建議這類醫療決策語意進入正式
    Observation，但供應商完整回應（例如便便判讀的 1-7 級與照護建議）對
    授權人員的覆核有價值。回傳這個信封時，raw 原樣存進 raw_ai_output
    （本來就是給授權覆核看的欄位），只有 formal 走驗證、成為正式建議。
    回傳普通 dict 的既有供應商行為完全不變。
    """

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
