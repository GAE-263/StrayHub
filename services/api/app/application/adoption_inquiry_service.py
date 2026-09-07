from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.models.adoption_inquiry import AdoptionInquiry

# 目前最小可用版本：submitted（剛送出，尚未處理）／contacted（工作人員已聯繫）
# 兩種狀態，比照毛孩日記收件匣的已讀/未讀設計。之後如果需要更完整的審核
# 流程（核准/婉拒等），再另外擴充，不在這次範圍內。
VALID_STATUSES = {"new", "contacted"}

# 問卷代碼 -> 中文標籤／選項顯示文字，給「查看問卷」用——刻意跟
# line_webhook.py 的 _ADOPTION_QUESTION_LABEL/_ADOPTION_QUESTION_OPTIONS、
# adoption_ai_analysis_service.py 的 _ANSWER_LABELS/_ANSWER_OPTIONS
# 各自維護一份小鏡子，不跨層（api -> application）互相 import，理由跟後者
# 的既有註解一致。三份要保持同步——之後若代碼/選項有異動記得一起改。
_QUESTION_LABEL: dict[str, str] = {
    "housing_type": "居住環境",
    "dog_experience": "養狗經驗",
    "other_pets": "家中其他寵物",
    "household_members": "家庭成員",
    "work_schedule": "作息時間",
    "preferred_size": "希望的體型",
    "preferred_energy": "希望的活動力",
    "parenting_style": "飼養風格",
    "patience_level": "耐心與應變",
    "adoption_motivation": "領養動機",
    "adopter_name": "姓名",
    "contact_time": "方便聯繫時間",
    "phone_number": "手機號碼",
}

_QUESTION_OPTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
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

_BASE_QUESTION_ORDER = (
    "housing_type",
    "dog_experience",
    "other_pets",
    "household_members",
    "work_schedule",
    "parenting_style",
    "patience_level",
    "adoption_motivation",
)
_CONTACT_INFO_ORDER = ("adopter_name", "contact_time", "phone_number")
_QUESTION_ORDER: dict[str, tuple[str, ...]] = {
    "specific_animal": _BASE_QUESTION_ORDER + _CONTACT_INFO_ORDER,
    "recommend_me": _BASE_QUESTION_ORDER
    + ("preferred_size", "preferred_energy")
    + _CONTACT_INFO_ORDER,
}


def _answer_display(key: str, value: str) -> str:
    for code, emoji, label in _QUESTION_OPTIONS.get(key, ()):
        if code == value:
            return f"{emoji} {label}"
    return value


def _display_answers(path: str, answers: dict[str, str]) -> list[dict[str, str]]:
    """Ordered, human-readable rows for "查看問卷" — code values (e.g.
    "apartment_small") resolved to their Chinese label, questions in the
    same order the adopter actually answered them in. Falls back to raw
    keys for anything outside the known order (shouldn't normally happen,
    but a stale/unexpected key is more useful shown than silently dropped)."""
    order = _QUESTION_ORDER.get(path, _BASE_QUESTION_ORDER + _CONTACT_INFO_ORDER)
    rows = [
        {"key": key, "label": _QUESTION_LABEL.get(key, key), "value": _answer_display(key, value)}
        for key in order
        if (value := answers.get(key)) is not None
    ]
    extra_keys = set(answers) - set(order)
    rows += [
        {
            "key": key,
            "label": _QUESTION_LABEL.get(key, key),
            "value": _answer_display(key, answers[key]),
        }
        for key in sorted(extra_keys)
    ]
    return rows


class AdoptionInquiryInboxService:
    """Staff-facing view of AdoptionInquiry rows submitted via the LINE
    adoption flow — this is a *different* inbox from ReportInboxService's
    care-report reviews; nothing here overlaps that table or that feature."""

    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id
        self.audit = AuditService(session)

    async def list(
        self,
        *,
        search: str | None = None,
        path: str | None = None,
        inquiry_status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        if path and path not in {"specific_animal", "recommend_me"}:
            raise DomainError("invalid_adoption_path", "不支援的領養路徑", 422)
        if inquiry_status and inquiry_status not in VALID_STATUSES:
            raise DomainError("invalid_adoption_inquiry_status", "不支援的領養意願狀態", 422)
        if from_date and to_date and from_date > to_date:
            raise DomainError("invalid_date_range", "開始日期不得晚於結束日期", 422)
        filters = [AdoptionInquiry.organization_id == self.organization_id]
        if path:
            filters.append(AdoptionInquiry.path == path)
        if inquiry_status:
            filters.append(AdoptionInquiry.status == inquiry_status)
        if from_date:
            filters.append(
                AdoptionInquiry.submitted_at
                >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
            )
        if to_date:
            filters.append(
                AdoptionInquiry.submitted_at
                <= datetime.combine(to_date, time.max, tzinfo=timezone.utc)
            )
        if search:
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            filters.append(
                or_(
                    AdoptionInquiry.animal_name_snapshot.ilike(pattern, escape="\\"),
                    AdoptionInquiry.shelter_number_snapshot.ilike(pattern, escape="\\"),
                    AdoptionInquiry.adopter_name.ilike(pattern, escape="\\"),
                    AdoptionInquiry.phone_number.ilike(pattern, escape="\\"),
                )
            )
        total = await self.session.scalar(
            select(func.count(AdoptionInquiry.id)).where(*filters)
        )
        rows = await self.session.execute(
            select(AdoptionInquiry)
            .where(*filters)
            .order_by(AdoptionInquiry.submitted_at.desc(), AdoptionInquiry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [self._payload(inquiry) for inquiry in rows.scalars()],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }

    async def set_status(
        self, inquiry_id: UUID, *, inquiry_status: str, actor_user_id: UUID
    ) -> dict:
        if inquiry_status not in VALID_STATUSES:
            raise DomainError(
                "invalid_adoption_inquiry_status", f"不支援的狀態：{inquiry_status}", 422
            )
        result = await self.session.execute(
            select(AdoptionInquiry)
            .where(
                AdoptionInquiry.id == inquiry_id,
                AdoptionInquiry.organization_id == self.organization_id,
            )
            .with_for_update()
        )
        inquiry = result.scalar_one_or_none()
        if inquiry is None:
            raise DomainError("adoption_inquiry_not_found", "找不到這筆領養意願", 404)
        previous_status = inquiry.status
        inquiry.status = inquiry_status
        inquiry.status_updated_at = datetime.now(timezone.utc)
        inquiry.status_updated_by_user_id = actor_user_id
        await self.session.flush()
        await self.audit.record(
            organization_id=self.organization_id,
            actor_user_id=actor_user_id,
            action="status_update",
            resource_type="adoption_inquiry",
            resource_id=inquiry.id,
            source_channel="api",
            before={"status": previous_status},
            after={"status": inquiry_status},
        )
        return self._payload(inquiry)

    @staticmethod
    def _payload(inquiry: AdoptionInquiry) -> dict:
        score, explanation = _resolve_ai_suitability(inquiry)
        return {
            "id": str(inquiry.id),
            "organization_id": str(inquiry.organization_id),
            "target_animal_id": str(inquiry.target_animal_id),
            "animal_name": inquiry.animal_name_snapshot,
            "shelter_number": inquiry.shelter_number_snapshot,
            "path": inquiry.path,
            "adopter_name": inquiry.adopter_name,
            "phone_number": inquiry.phone_number,
            "answers": inquiry.answers,
            "answers_display": _display_answers(inquiry.path, inquiry.answers),
            "status": inquiry.status,
            "staff_notes": inquiry.staff_notes,
            "submitted_at": inquiry.submitted_at.isoformat(),
            "status_updated_at": (
                inquiry.status_updated_at.isoformat() if inquiry.status_updated_at else None
            ),
            "ai_suitability_score": score,
            "ai_suitability_explanation": explanation,
            "ai_recommendation_overridden": inquiry.ai_recommendation_overridden,
        }


def _resolve_ai_suitability(inquiry: AdoptionInquiry) -> tuple[int | None, str | None]:
    """心有所屬 populates ai_suitability_score/explanation directly (one
    Gemini call scoring the single animal the adopter already picked — see
    _run_adoption_ai_suitability_analysis). 推薦名單 never writes those two
    columns — its AI output instead lives in match_scores_snapshot, a
    per-candidate list from the curation/reranking call. Both represent the
    same underlying idea (AI's assessment of adopter-animal fit), so the
    staff inbox shows one unified "AI 適配度" column: for 推薦名單, resolved
    here as the snapshot entry for whichever animal the adopter actually
    ended up submitting for (their target_animal_id) — which may or may not
    be the AI's top pick, especially when ai_recommendation_overridden.

    Deliberately not a generic "whichever is present" fallback: 心有所屬's
    own match_scores_snapshot is a *rule-based* score on a 0-1 scale (see
    AdoptionMatchingService.score_target), not the AI's 0-100 — falling back
    to it when the AI call genuinely didn't run would show a misleadingly-
    scaled number rather than the honest "no AI data" it actually is."""
    if inquiry.ai_suitability_score is not None:
        return inquiry.ai_suitability_score, inquiry.ai_suitability_explanation
    if inquiry.path != "recommend_me":
        return None, None
    for entry in inquiry.match_scores_snapshot or []:
        if entry.get("animal_id") == str(inquiry.target_animal_id):
            score = entry.get("score")
            reasons = entry.get("reasons") or []
            return (
                int(score) if isinstance(score, (int, float)) else None,
                "；".join(reasons) if reasons else None,
            )
    return None, None
