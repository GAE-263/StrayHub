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

# housing_type/dog_experience/other_pets/household_members/work_schedule are
# shared by both adoption paths; preferred_size/preferred_energy only apply
# to 推薦名單. Kept separate from _ANSWER_LABELS/_ANSWER_OPTIONS below (which
# cover all 10) so extract_profile can ask for the right subset per path
# without importing AdoptionPath's REQUIRED_KEYS_BY_PATH here — this module
# stays a pure Gemini-prompting layer, agnostic of the state machine.
BASE_PROFILE_KEYS: tuple[str, ...] = (
    "housing_type",
    "dog_experience",
    "other_pets",
    "household_members",
    "work_schedule",
    "parenting_style",
    "patience_level",
    "adoption_motivation",
)
RECOMMEND_ME_EXTRA_PROFILE_KEYS: tuple[str, ...] = ("preferred_size", "preferred_energy")

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

# Mirrors _ADOPTION_QUESTION_OPTIONS in line_webhook.py (same reason as
# _ANSWER_LABELS above) — each question's raw stored code, mapped to the same
# emoji + Chinese label the adopter actually saw when answering. Gemini gets
# this instead of the bare code (e.g. "小坪數公寓" instead of
# "apartment_small") so what it reasons over matches what a human reviewer
# would read, not an internal implementation detail.
_ANSWER_OPTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "housing_type": (
        ("house", "🏡", "透天／獨棟房屋"),
        ("apartment_small", "🏢", "小坪數公寓"),
        ("apartment_large", "🏙️", "大坪數公寓"),
    ),
    "dog_experience": (
        ("first_time", "🌱", "這是我第一次"),
        ("experienced", "🎓", "有，養過囉"),
    ),
    "other_pets": (
        ("none", "🚫", "目前沒有其他寵物"),
        ("has_cats", "🐱", "家裡有貓咪"),
        ("has_dogs", "🐶", "家裡有其他狗狗"),
    ),
    "household_members": (
        ("adults_only", "🧑", "只有大人"),
        ("has_children", "👶", "家裡有小朋友"),
    ),
    "work_schedule": (
        ("work_from_home", "💻", "在家工作"),
        ("flexible", "🌤️", "工作時間很彈性"),
        ("full_time_work", "🏢", "全職外出上班"),
        ("little_time_at_home", "🌙", "在家時間比較少"),
        ("retired", "🌿", "退休／幾乎都在家"),
    ),
    "preferred_size": (
        ("small", "🐕‍🦺", "小型犬"),
        ("medium", "🐕", "中型犬"),
        ("large", "🐩", "大型犬"),
    ),
    "preferred_energy": (
        ("low", "😌", "文靜乖巧"),
        ("medium", "🙂", "適中就好"),
        ("high", "🤩", "活潑好動"),
    ),
    "parenting_style": (
        ("structured", "📏", "生活作息比較固定規律"),
        ("free", "🌿", "比較彈性隨性"),
    ),
    "patience_level": (
        ("high_patience", "😌", "很有耐心，慢慢教就好"),
        ("medium_patience", "🙂", "看情況，需要一點時間適應"),
        ("low_patience", "😅", "希望毛孩本來就乖巧穩定"),
    ),
    "adoption_motivation": (
        ("companionship", "🥰", "想要一個陪伴"),
        ("family_activity", "🏃", "想帶著一起運動出遊"),
        ("guarding", "🛡️", "希望多一點安全感"),
        ("other_reason", "💬", "其他原因"),
    ),
}


def _answer_display(key: str, value: str) -> str:
    """Falls back to the raw stored value for anything not in the table
    (e.g. free-text answers) rather than dropping the answer entirely."""
    for code, emoji, label in _ANSWER_OPTIONS.get(key, ()):
        if code == value:
            return f"{emoji} {label}"
    return value


def _build_extraction_prompt(text: str, keys: tuple[str, ...]) -> str:
    """One call replaces the first ask of each preference question: the
    adopter writes a free-text self-introduction instead of answering N
    separate taps, and Gemini reads it for whichever of these fields it
    can confidently place — see line_webhook.py's AWAITING_FREETEXT_PROFILE.
    Every field is optional in the output; a field genuinely not covered by
    the text (or one the adopter's wording doesn't clearly map to any of the
    listed options) should come back null rather than guessed, since a wrong
    guess here would silently feed the AI suitability analysis downstream
    with an answer the adopter never actually gave."""
    field_lines = "\n".join(
        f"- {_ANSWER_LABELS.get(key, key)}（{key}）："
        + "、".join(f'"{code}"={label}' for code, _emoji, label in _ANSWER_OPTIONS.get(key, ()))
        for key in keys
    )
    keys_json = ", ".join(f'"{key}": "<代碼或 null>"' for key in keys)
    return (
        "你是一位動物收容所的領養媒合助手。領養者剛用一段自由文字自我介紹，請從這段文字裡"
        "判斷以下每一項，各自屬於哪一個選項代碼。只有文字內容明確對應到某個選項時才填那個"
        "代碼；文字沒有提到、或含意模糊、無法確定對應哪個選項時，該項一律回傳 null，"
        "不要用猜的、也不要自己發明代碼。\n\n"
        f"欄位與選項：\n{field_lines}\n\n"
        f"領養者的自我介紹：\n「{text}」\n\n"
        f"請只回傳 JSON，格式為 {{{keys_json}}}，代碼必須完全照抄上面列出的選項代碼，"
        "不要有其他文字或 markdown 標記。"
    )


def profile_extraction_contract(
    *, include_recommend_me_keys: bool
) -> tuple[tuple[str, ...], dict[str, set[str]]]:
    """Return the existing questionnaire allowlist without exposing webhook internals."""
    extra = RECOMMEND_ME_EXTRA_PROFILE_KEYS if include_recommend_me_keys else ()
    keys = BASE_PROFILE_KEYS + extra
    return keys, {
        key: {code for code, _emoji, _label in _ANSWER_OPTIONS.get(key, ())} for key in keys
    }


def build_profile_extraction_prompt(
    text: str, *, include_recommend_me_keys: bool
) -> tuple[str, dict[str, set[str]]]:
    keys, valid_values = profile_extraction_contract(
        include_recommend_me_keys=include_recommend_me_keys
    )
    return _build_extraction_prompt(text, keys), valid_values


def build_profile_summary_rows(
    *, include_recommend_me_keys: bool, answers: dict[str, str]
) -> list[tuple[str, str]]:
    keys, _valid_values = profile_extraction_contract(
        include_recommend_me_keys=include_recommend_me_keys
    )
    return [
        (
            _ANSWER_LABELS[key],
            _answer_display(key, answers[key]) if key in answers else "待確認",
        )
        for key in keys
    ]


def _describe_animal(animal: Animal) -> str:
    temperament = "、".join(animal.temperament or []) or "未提供"
    return (
        f"名字：{animal.name}；品種：{animal.breed or '未提供'}；"
        f"體型：{animal.size or '未提供'}；活動力：{animal.energy or '未提供'}；"
        f"性別：{animal.sex or '未提供'}；個性標籤：{temperament}；"
        f"領養須知：{animal.adoption_notes or '無'}"
    )


# A soft nudge, not a numeric formula: no in-house outcome data exists yet
# to justify fixed weights (see docs discussion), so this only tells Gemini
# which dimensions to lean on when the answers pull in different directions.
# Only "dog_experience" and "patience_level" are named — not because the
# other 6 questions don't matter, but because these two are the ones with
# actual published evidence behind them (checked before writing this, after
# an earlier draft named housing_type/parenting_style with no real backing):
#
# - First-time owners were markedly more likely than experienced owners to
#   return their dog within 6 months of adoption — Kelley et al., "Returning
#   a Shelter Dog: The Role of Owner Expectations and Dog Behavior" (2022),
#   https://pmc.ncbi.nlm.nih.gov/articles/PMC9100056/
# - The same study found returning owners held unrealistic expectations
#   about the dog's behaviour/emotional bond settling in quickly, while most
#   behavioural issues actually eased over the first ~4 months — i.e.
#   patience through that adjustment window tracks with the dog staying
#   adopted.
#
# housing_type was deliberately dropped from this hint: the literature on
# housing-related relinquishment is about instability (renting, landlord
# pet restrictions) — see "Housing-related companion animal relinquishment
# across 21 animal shelters in the United States from 2019-2023" (Frontiers,
# 2024), https://www.frontiersin.org/journals/veterinary-science/articles/10.3389/fvets.2024.1430388/full
# — and explicitly pushes back on assuming a dog's size/space needs predict
# it from square footage alone. Our own housing_type question only asks
# house/small-apartment/large-apartment, which isn't what that research
# actually measured, so it doesn't support a priority claim here. See also
# the general relinquishment risk-factor literature: Patronek et al., "Risk
# Factors for Relinquishment of Dogs to an Animal Shelter" (1996),
# https://www.researchgate.net/publication/14446640_Risk_Factors_For_Relinquishment_Of_Dogs_To_An_Animal_Shelter
# and Diesel et al., "Factors Informing the Return of Adopted Dogs and Cats
# to an Animal Shelter" (2010), https://pmc.ncbi.nlm.nih.gov/articles/PMC7552273/
#
# parenting_style ("structured" vs "free" daily routine) has no matching
# study at all as far as this search found — left out rather than guessed at.
#
# Revisit this whole hint once growth-diary "concern" outcomes give
# something real, in-house to calibrate against instead of borrowed
# literature — see AdoptionInquiry.ai_suitability_score / GrowthDiaryEntry.ai_mood.
_SUITABILITY_PRIORITY_HINT = (
    "若各項條件之間有衝突或難以取捨，請優先參考「養狗經驗」與「耐心與應變」這兩項——"
    "根據國外收容犬送養追蹤研究，第一次養狗的飼主明顯比有經驗的飼主更容易在領養後"
    "6 個月內退養；同一份研究也發現，退養的飼主普遍對狗的行為與情感連結抱有過高期待，"
    "而多數行為問題其實會在領養後前 4 個月內逐漸改善，顯示能否撐過磨合期是實際影響"
    "穩定度的關鍵。"
)

# Companion note to the housing_type answer specifically — see the
# housing_type discussion above (Frontiers 2024): the actual relinquishment
# risk factor in the literature is housing *instability* (renting, landlord
# pet restrictions), not square footage, and that same study pushes back on
# assuming a dog's size dictates whether an apartment suits it. Our own
# housing_type question only captures square footage (house / small
# apartment / large apartment), so this stops Gemini from over-reading "small
# apartment" as a hard mismatch for a larger or more energetic animal.
_HOUSING_SIZE_CAVEAT = (
    "補充說明：居住坪數大小不是判斷適合度的絕對標準——研究顯示大型犬不一定不適合小"
    "坪數住所，重點在於飼主能否提供足夠的活動與互動機會，請勿僅因居住環境坪數較小"
    "就判定不適合特定體型的動物。"
)


def _build_suitability_prompt(answers: dict, animal: Animal) -> str:
    answer_lines = "\n".join(
        f"- {_ANSWER_LABELS.get(key, key)}：{_answer_display(key, value)}"
        for key, value in answers.items()
        if key in _ANSWER_LABELS
    )
    return (
        "你是一位資深的動物收容所領養媒合顧問。請根據以下領養者問卷答案，評估他們與這隻"
        "動物的適配程度，用 0-100 的整數評分（分數越高代表越適合），並附上一段簡短、溫暖、"
        "口語化的中文說明（100 字以內），指出具體的適配或需要留意之處。"
        f"{_SUITABILITY_PRIORITY_HINT}\n\n"
        f"領養者問卷：\n{answer_lines}\n\n"
        f"{_HOUSING_SIZE_CAVEAT}\n\n"
        f"動物資料：\n{_describe_animal(animal)}\n\n"
        '請只回傳 JSON，格式為 {"score": <0-100整數>, "explanation": "<說明文字>"}，'
        "不要有其他文字或 markdown 標記。"
    )


def build_suitability_prompt(answers: dict, animal: Animal) -> str:
    """Public pure prompt builder for durable execution services."""
    return _build_suitability_prompt(answers, animal)


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


def build_alternatives_prompt(special_request: str, candidates: list[Animal]) -> str:
    """Build the existing bounded-candidate prompt for durable workers."""
    return _build_alternatives_prompt(special_request, candidates)


def _build_recommendation_prompt(answers: dict, candidates: list[Animal]) -> str:
    answer_lines = "\n".join(
        f"- {_ANSWER_LABELS.get(key, key)}：{_answer_display(key, value)}"
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
        f"口語化的中文說明（60 字以內）。{_SUITABILITY_PRIORITY_HINT}\n\n"
        f"領養者問卷：\n{answer_lines}\n\n"
        f"{_HOUSING_SIZE_CAVEAT}\n\n"
        f"候選毛孩清單：\n{candidate_lines}\n\n"
        '請只回傳 JSON，格式為 {"recommendations": [{"animal_id": "<必須是清單中的 id，'
        '原樣照抄，不可自行編造>", "score": <0-100整數>, "explanation": "<說明文字>"}]}，'
        "依你認為最適合排序，最多 5 筆，不要有其他文字或 markdown 標記。"
    )


def build_recommendation_prompt(answers: dict, candidates: list[Animal]) -> str:
    """Build the existing curation prompt from frozen preferences and candidates."""
    return _build_recommendation_prompt(answers, candidates)


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

    async def extract_profile(
        self, *, text: str, include_recommend_me_keys: bool
    ) -> dict[str, str]:
        """One round of AWAITING_FREETEXT_PROFILE — see line_webhook.py.
        include_recommend_me_keys adds preferred_size/preferred_energy for
        推薦名單; 心有所屬 never asks those. Always returns a dict (possibly
        empty) rather than None — "nothing extracted" isn't a distinct
        failure the caller needs to branch on."""
        prompt, valid_values = build_profile_extraction_prompt(
            text, include_recommend_me_keys=include_recommend_me_keys
        )
        return await self.gemini.extract_adoption_profile(prompt, valid_values=valid_values)

    async def recommend_alternatives(
        self, *, special_request: str, exclude_animal_id: UUID
    ) -> list[tuple[Animal, str]] | None:
        """None means the call itself failed or produced nothing usable;
        an empty list means there was simply no other adoptable animal to
        suggest — callers should tell these apart when wording the fallback
        message."""
        candidates = await AnimalRepository(
            self.session, self.organization_id
        ).list_adoptable_excluding(exclude_animal_id, limit=30)
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
