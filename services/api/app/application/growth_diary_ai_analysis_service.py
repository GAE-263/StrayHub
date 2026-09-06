"""Background (never inline-with-reply) AI analysis for 毛孩日記 entries — one
Gemini call per entry produces two different outputs from the same input:

1. A reply shown to the adopter — warm encouragement for a plain status
   update, but a genuine, educational answer (correct care/behaviour
   guidance, not just sympathy) when the note contains an adoption-related
   question. The goal (per shelter staff's own framing) is to actively help
   first-time adopters through the adjustment period and reduce return/
   abandonment by getting them correct information in the moment, not just
   a kind word.
2. An objective health/behaviour observation summary written into the entry
   record for shelter staff.

The photo itself (not just its presence) is sent to Gemini as multimodal
input when one was shared — see gemini_client.py's `analyze_growth_diary_
entry` — so a photo-only entry (no text note) can be genuinely analyzed, not
just acknowledged. No LINE messaging here — line_webhook.py owns building/
pushing messages."""

from __future__ import annotations

from services.api.app.infrastructure.ai.gemini_client import (
    GeminiClient,
    GeminiGrowthDiaryAnalysis,
)


def _build_growth_diary_prompt(*, animal_name: str, note: str | None, has_photo: bool) -> str:
    if note and has_photo:
        subject = f"領養者剛分享了以下關於「{animal_name}」的近況，同時附上一張照片：\n\n「{note}」"
        instruction = "請同時參考文字內容和照片畫面"
    elif note:
        subject = f"領養者剛分享了以下關於「{animal_name}」的近況：\n\n「{note}」"
        instruction = "請根據文字內容"
    else:
        subject = f"領養者剛分享了一張「{animal_name}」的近況照片，沒有附加文字說明。"
        instruction = "請直接觀察照片畫面（例如毛孩的體態、精神狀態、環境、有無明顯外傷或異常）"
    return (
        f"你是一位親切但專業的動物收容所「毛孩日記」分析助手。{subject}\n\n"
        f"{instruction}，完成三件事：\n"
        "1. 判斷這則分享的整體狀況，分類為 positive（適應良好，無需特別介入）、"
        "neutral（例行回報，無異常）或 concern（需留意，例如疑似生病、行為異常、"
        "體態明顯消瘦或受傷、領養者表達困擾或求助）。\n"
        "2. 寫一段給領養者看的回覆：\n"
        "   - 如果內容裡包含跟領養、飼養相關的疑問或求助（例如行為問題、健康照護、"
        "飲食、訓練、居家環境、社會化、磨合期適應等），你「必須」根據正確的飼養"
        "知識具體回答，給出實際可行的建議，並在合適時教育正確的飼養觀念——目的是"
        "協助新手飼主順利度過磨合期、降低棄養風險，不能只安慰帶過或迴避問題"
        "（150 字以內；如果單一回覆裝不下完整答案，優先把最關鍵的處理方式講清楚）。"
        "如果問題明顯超出一般飼養常識範圍、涉及疑似疾病診斷或需要親自檢查才能判斷，"
        "在給出初步建議後提醒飼主儘快諮詢獸醫或聯繫收容所工作人員，不要臆測診斷。\n"
        "   - 如果只是單純近況分享、沒有疑問，就給予溫暖、口語化的鼓勵或肯定"
        "（100 字以內）。\n"
        "3. 寫一段給收容所工作人員看的客觀健康／行為觀察摘要（60 字以內），語氣"
        "專業、精簡，不需要暖場問候；如果領養者有提問，也請簡述問了什麼、AI 給了"
        "什麼方向的建議，方便工作人員追蹤。\n\n"
        '請只回傳 JSON，格式為 {"mood": "positive|neutral|concern", '
        '"adopter_reply": "<給領養者的回覆>", "staff_summary": "<給工作人員的摘要>"}，'
        "不要有其他文字或 markdown 標記。"
    )


class GrowthDiaryAiAnalysisService:
    def __init__(self, gemini: GeminiClient) -> None:
        self.gemini = gemini

    async def analyze_entry(
        self,
        *,
        animal_name: str,
        note: str | None,
        photo: bytes | None = None,
        photo_mime_type: str | None = None,
    ) -> GeminiGrowthDiaryAnalysis | None:
        if not note and photo is None:
            return None
        prompt = _build_growth_diary_prompt(
            animal_name=animal_name, note=note, has_photo=photo is not None
        )
        return await self.gemini.analyze_growth_diary_entry(
            prompt, image=photo, image_mime_type=photo_mime_type
        )


__all__ = ["GrowthDiaryAiAnalysisService"]
