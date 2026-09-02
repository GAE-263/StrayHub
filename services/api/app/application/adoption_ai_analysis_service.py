"""Background (never inline-with-reply) AI analysis for the two adoption
paths. Three independent calls to Gemini:

1. `analyze_suitability` (心有所屬) — 8-question answers + the chosen
   animal's profile -> a 0-100 score and a short explanation.
2. `recommend_alternatives` (心有所屬, low score) — a free-text special
   request the adopter typed in response to a low score, + every other
   adoptable animal in the same shelter -> 2-3 AI-picked alternatives with a
   reason each.
3. `curate_recommendations` (推薦名單) — the 10-question answers + a
   rule-filtered candidate pool (already narrowed down, not every adoptable
   animal) -> that same pool reranked with a 0-100 score and explanation
   each, so the adopter sees an AI-curated list instead of a purely
   rule-based one.

No LINE messaging here — this module only talks to Postgres and Gemini.
`line_webhook.py` owns building/pushing the Flex cards, since it's the one
holding the `LineMessagingPort` for the request."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.infrastructure.ai.gemini_client import (
    GeminiAnimalRecommendation,
    GeminiClient,
    GeminiRankedRecommendation,
    GeminiSuitabilityResult,
)
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.repositories.animal_repository import AnimalRepository

# Mirrors _ADOPTION_QUESTION_LABEL / _answer_display in line_webhook.py, but
# duplicated here rather than imported — that module is the API/webhook
# layer and importing from it here would invert the dependency direction.
_ANSWER_LABELS: dict[str, str] = {
    "housing_type": "居住環境",
    "dog_experience": "養狗經驗",
    "other_pets": "家中其他寵物",
    "household_members": "家庭成員",
    "work_schedule": "作息時間",
    "parenting_style": "飼養風格",
    "patience_level": "耐心與應變",
    "adoption_motivation": "領養動機",
    "preferred_size": "希望的體型",
    "preferred_energy": "希望的活動力",
}


def _describe_animal(animal: Animal) -> str:
    temperament = "、".join(animal.temperament or []) or "未提供"
    return (
        f"名字：{animal.name}；品種：{animal.breed or '未提供'}；"
        f"體型：{animal.size or '未提供'}；活動力：{animal.energy or '未提供'}；"
        f"性別：{animal.sex or '未提供'}；個性標籤：{temperament}；"
        f"領養須知：{animal.adoption_notes or '無'}"
    )


def _build_suitability_prompt(answers: dict, animal: Animal) -> str:
    answer_lines = "\n".join(
        f"- {_ANSWER_LABELS.get(key, key)}：{value}"
        for key, value in answers.items()
        if key in _ANSWER_LABELS
    )
    return (
        "你是一位資深的動物收容所領養媒合顧問。請根據以下領養者問卷答案，評估他們與這隻"
        "動物的適配程度，用 0-100 的整數評分（分數越高代表越適合），並附上一段簡短、溫暖、"
        "口語化的中文說明（100 字以內），指出具體的適配或需要留意之處。\n\n"
        f"領養者問卷：\n{answer_lines}\n\n"
        f"動物資料：\n{_describe_animal(animal)}\n\n"
        '請只回傳 JSON，格式為 {"score": <0-100整數>, "explanation": "<說明文字>"}，'
        "不要有其他文字或 markdown 標記。"
    )


def _build_alternatives_prompt(special_request: str, candidates: list[Animal]) -> str:
    candidate_lines = "\n".join(
        f"- id: {candidate.id}；{_describe_animal(candidate)}" for candidate in candidates
    )
    return (
        "領養者原本考慮的動物合拍度較低，並提出了額外的期待或特殊需求：\n"
        f"「{special_request}」\n\n"
        "請從以下同一間收容所的可領養動物清單中，挑選 2 到 3 隻最符合這個需求的動物，"
        "各附一句簡短的中文推薦理由（30 字以內）。\n\n"
        f"動物清單：\n{candidate_lines}\n\n"
        '請只回傳 JSON，格式為 {"recommendations": [{"animal_id": "<必須是清單中的 id，'
        '原樣照抄，不可自行編造>", "reason": "<推薦理由>"}]}，最多 3 筆，不要有其他文字或'
        " markdown 標記。"
    )


def _build_recommendation_prompt(answers: dict, candidates: list[Animal]) -> str:
    answer_lines = "\n".join(
        f"- {_ANSWER_LABELS.get(key, key)}：{value}"
        for key, value in answers.items()
        if key in _ANSWER_LABELS
    )
    candidate_lines = "\n".join(
        f"- id: {candidate.id}；{_describe_animal(candidate)}" for candidate in candidates
    )
    return (
        "你是一位資深的動物收容所領養媒合顧問。以下是領養者的問卷答案，以及系統已依條件"
        "篩選出的候選毛孩清單（這批已經是相對接近的一批，不是收容所全部動物）。請你重新"
        "評估每一隻與領養者的適配程度，各給一個 0-100 的整數評分，並各附一句簡短、溫暖、"
        "口語化的中文說明（60 字以內）。\n\n"
        f"領養者問卷：\n{answer_lines}\n\n"
        f"候選毛孩清單：\n{candidate_lines}\n\n"
        '請只回傳 JSON，格式為 {"recommendations": [{"animal_id": "<必須是清單中的 id，'
        '原樣照抄，不可自行編造>", "score": <0-100整數>, "explanation": "<說明文字>"}]}，'
        "依你認為最適合排序，最多 5 筆，不要有其他文字或 markdown 標記。"
    )


class AdoptionAiAnalysisService:
    def __init__(self, session: AsyncSession, organization_id: UUID, gemini: GeminiClient) -> None:
        self.session = session
        self.organization_id = organization_id
        self.gemini = gemini

    async def analyze_suitability(
        self, *, answers: dict, animal: Animal
    ) -> GeminiSuitabilityResult | None:
        prompt = _build_suitability_prompt(answers, animal)
        return await self.gemini.analyze_suitability(prompt)

    async def recommend_alternatives(
        self, *, special_request: str, exclude_animal_id: UUID
    ) -> list[tuple[Animal, str]] | None:
        """None means the call itself failed or produced nothing usable;
        an empty list means there was simply no other adoptable animal to
        suggest — callers should tell these apart when wording the fallback
        message."""
        animals = await AnimalRepository(self.session, self.organization_id).list_adoptable()
        candidates = [animal for animal in animals if animal.id != exclude_animal_id]
        if not candidates:
            return []
        prompt = _build_alternatives_prompt(special_request, candidates)
        recommendations = await self.gemini.recommend_alternatives(
            prompt, valid_animal_ids={str(candidate.id) for candidate in candidates}
        )
        if recommendations is None:
            return None
        by_id = {str(candidate.id): candidate for candidate in candidates}
        return [
            (by_id[rec.animal_id], rec.reason) for rec in recommendations if rec.animal_id in by_id
        ]

    async def curate_recommendations(
        self, *, answers: dict, candidates: list[Animal]
    ) -> list[tuple[Animal, int, str]] | None:
        """None means the Gemini call itself failed — callers should fall
        back to the rule-based ordering already in `candidates`. An empty
        list only happens if `candidates` was empty to begin with."""
        if not candidates:
            return []
        prompt = _build_recommendation_prompt(answers, candidates)
        ranked = await self.gemini.rank_recommendations(
            prompt, valid_animal_ids={str(candidate.id) for candidate in candidates}
        )
        if ranked is None:
            return None
        by_id = {str(candidate.id): candidate for candidate in candidates}
        return [
            (by_id[item.animal_id], item.score, item.explanation)
            for item in ranked
            if item.animal_id in by_id
        ]


__all__ = [
    "AdoptionAiAnalysisService",
    "GeminiAnimalRecommendation",
    "GeminiRankedRecommendation",
    "GeminiSuitabilityResult",
]
