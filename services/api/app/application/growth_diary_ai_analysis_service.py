"""Background (never inline-with-reply) AI analysis for 毛孩日記 entries — one
Gemini call per entry produces two different outputs from the same input:

1. A warm, encouraging reply shown to the adopter.
2. An objective health/behaviour observation summary written into the entry
   record for shelter staff.

Photo-only entries (no text note) skip the Gemini call entirely — this
project's Gemini integration is text-only so far (see gemini_client.py); a
real multimodal analysis of the photo itself is future work. No LINE
messaging here — line_webhook.py owns building/pushing messages."""

from __future__ import annotations

from dataclasses import dataclass

from services.api.app.infrastructure.ai.gemini_client import (
    GeminiClient,
    GeminiGrowthDiaryAnalysis,
)

GROWTH_DIARY_PROMPT_VERSION = "growth-diary-v1"
GROWTH_DIARY_OUTPUT_SCHEMA_VERSION = "growth-diary-analysis-v1"


@dataclass(frozen=True)
class GrowthDiaryAiAnalysisResult:
    mood: str
    adopter_reply: str
    staff_summary: str
    provider: str
    model_name: str
    model_version: str
    prompt_version: str
    output_schema_version: str
    raw_output: str | None


def _build_growth_diary_prompt(*, animal_name: str, note: str, has_photo: bool) -> str:
    photo_note = "（領養者同時附上一張照片，但你目前只看得到文字內容）" if has_photo else ""
    return (
        "你是一位親切但專業的動物收容所「毛孩日記」分析助手。領養者剛分享了以下關於"
        f"「{animal_name}」的近況{photo_note}：\n\n"
        f"「{note}」\n\n"
        "請完成三件事：\n"
        "1. 判斷這則分享的整體狀況，分類為 positive（適應良好，無需特別介入）、"
        "neutral（例行回報，無異常）或 concern（需留意，例如疑似生病、行為異常、"
        "領養者表達困擾或求助）。\n"
        "2. 寫一段給領養者看的溫暖、口語化回覆（100 字以內），根據內容給予鼓勵、"
        "肯定或（concern 時）具體建議。\n"
        "3. 寫一段給收容所工作人員看的客觀健康／行為觀察摘要（60 字以內），語氣"
        "專業、精簡，不需要暖場問候。\n\n"
        '請只回傳 JSON，格式為 {"mood": "positive|neutral|concern", '
        '"adopter_reply": "<給領養者的回覆>", "staff_summary": "<給工作人員的摘要>"}，'
        "不要有其他文字或 markdown 標記。"
    )


class GrowthDiaryAiAnalysisService:
    def __init__(self, gemini: GeminiClient) -> None:
        self.gemini = gemini

    async def analyze_entry(
        self, *, animal_name: str, note: str | None, has_photo: bool
    ) -> GrowthDiaryAiAnalysisResult | None:
        if not note:
            return None
        prompt = _build_growth_diary_prompt(animal_name=animal_name, note=note, has_photo=has_photo)
        result: GeminiGrowthDiaryAnalysis | None = await self.gemini.analyze_growth_diary_entry(
            prompt
        )
        if result is None:
            return None
        return GrowthDiaryAiAnalysisResult(
            mood=result.mood,
            adopter_reply=result.adopter_reply,
            staff_summary=result.staff_summary,
            provider="google_gemini",
            model_name=self.gemini.model_name,
            model_version=self.gemini.model_name,
            prompt_version=GROWTH_DIARY_PROMPT_VERSION,
            output_schema_version=GROWTH_DIARY_OUTPUT_SCHEMA_VERSION,
            raw_output=result.raw_output,
        )


__all__ = ["GrowthDiaryAiAnalysisResult", "GrowthDiaryAiAnalysisService"]
