from __future__ import annotations

# LINE message payloads intentionally mirror the Messaging API's nested JSON
# shape; E501 is suppressed for those literal payloads only.
# ruff: noqa: E501
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Header, Request
from services.api.app.api.errors import DomainError
from services.api.app.application.adoption_ai_analysis_service import AdoptionAiAnalysisService
from services.api.app.application.ai_job_dispatch import create_growth_diary_analysis_job
from services.api.app.application.animal_selection import (
    AnimalSelectionService,
    TodayAnimalListService,
)
from services.api.app.application.care_report_handoff_service import (
    CareReportHandoffService,
)
from services.api.app.application.celery_job_dispatch import dispatch_ai_job
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.application.growth_diary_ai_analysis_service import (
    GrowthDiaryAiAnalysisService,
)
from services.api.app.application.line_adoption_conversation import (
    LineAdoptionConversationService,
)
from services.api.app.application.line_adoption_draft_service import LineAdoptionDraftService
from services.api.app.application.line_adoption_flex import (
    AiSuitabilityCard,
    MatchReportCard,
    QuestionOption,
    ShelterCard,
    build_ai_suitability_card,
    build_animal_confirm_card,
    build_info_card,
    build_match_report,
    build_question_card,
    build_shelter_carousel,
    build_target_animal_picker,
)
from services.api.app.application.line_draft_conversation import (
    LineDraftConversationService,
)
from services.api.app.application.line_draft_service import LineDraftService
from services.api.app.application.line_growth_diary_flex import (
    AdoptedAnimalOption,
    GrowthDiaryHistoryEntry,
    build_animal_picker,
    build_growth_diary_ai_reply_card,
    build_growth_diary_history_carousel,
    growth_diary_quick_reply_items,
)
from services.api.app.application.line_image_service import LineImageService
from services.api.app.application.line_menu_actions import (
    MENU_LIFF_ACTIONS,
    MENU_PLACEHOLDER_ACTIONS,
    STAFF_MENU_ACTIONS,
)
from services.api.app.application.line_message_presenter import (
    BUTTER,
    LILAC,
    PEACH,
    SKY,
    animal_confirmation_bubble,
    celebration_bubble,
    daily_care_bubble,
    prompt_bubble,
    question_bubble,
    summary_bubble,
)
from services.api.app.application.line_qr_image_decoder import decode_qr_image
from services.api.app.application.line_rich_menu_routing import (
    LineRole,
    RichMenuRoutingService,
    build_registry,
)
from services.api.app.application.line_webhook_session import LineWebhookSessionService
from services.api.app.application.media_access import (
    VOLUNTEER_WALK_PHOTO,
    ExternalAnimalPhotoService,
    issue_adoption_photo_token,
    issue_growth_diary_photo_token,
)
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.application.ports.line_messaging import LineMessagingPort
from services.api.app.application.report_job_dispatch import ReportJobDispatchService
from services.api.app.application.volunteer_reporting_authorization import (
    VolunteerReportingAuthorizationService,
)
from services.api.app.config.settings import get_settings
from services.api.app.domain.line_adoption_state import (
    CONTACT_EDIT_STATES,
    AdoptionDraftAnswers,
    AdoptionDraftState,
    AdoptionDraftStateMachine,
    AdoptionPath,
)
from services.api.app.domain.line_care_report_state import (
    REQUIRED_ANSWER_KEYS,
    UNOBSERVED,
    DraftAnswers,
    DraftState,
    DraftStateMachine,
)
from services.api.app.domain.line_webhook_security import verify_line_signature
from services.api.app.infrastructure.ai.gemini_client import GeminiClient
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope
from services.api.app.observability.logging import get_logger
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import (
    set_authentication_user_scope,
    set_organization_scope,
)
from services.api.app.persistence.models.growth_diary import GrowthDiaryDraft, GrowthDiaryEntry
from services.api.app.persistence.models.identity import LineUserBinding, Organization, User
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
)
from services.api.app.persistence.repositories.adoption_inquiry_repository import (
    AdoptionInquiryRepository,
    list_inquiries_for_adopter,
)
from services.api.app.persistence.repositories.ai_job_repository import AIJobRepository
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.care_report_handoff_repository import (
    CareReportHandoffRepository,
)
from services.api.app.persistence.repositories.care_report_repository import CareReportRepository
from services.api.app.persistence.repositories.growth_diary_repository import (
    GrowthDiaryRepository,
    list_entries_for_inquiries,
)
from services.api.app.persistence.repositories.growth_diary_repository import (
    clear_pending_draft as clear_pending_growth_diary_draft,
)
from services.api.app.persistence.repositories.growth_diary_repository import (
    get_pending_draft as get_pending_growth_diary_draft,
)
from services.api.app.persistence.repositories.growth_diary_repository import (
    set_pending_draft as set_pending_growth_diary_draft,
)
from services.api.app.persistence.repositories.line_webhook_repository import LineWebhookRepository
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from services.api.app.persistence.repositories.organization_repository import OrganizationRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from sqlalchemy import select

router = APIRouter(prefix="/v1/line", tags=["LINE Bot"])
logger = get_logger(__name__)


@dataclass
class _GrowthDiaryStoredPhoto:
    storage: Any
    organization_id: UUID
    object_key: str


@dataclass
class _GrowthDiaryPostCommit:
    line: Any
    event: dict
    line_user_id: str | None
    organization_id: UUID
    entry_id: UUID
    animal_name: str
    note: str | None
    has_photo: bool
    ai_job_id: UUID | None
    legacy_ai: bool


class _GrowthDiaryEventBoundary:
    """Own one event's object compensation and post-commit side effects."""

    def __init__(self, *, event_id: str, background_tasks: BackgroundTasks) -> None:
        self.event_id = event_id
        self.background_tasks = background_tasks
        self.stored_photo: _GrowthDiaryStoredPhoto | None = None
        self.post_commit: _GrowthDiaryPostCommit | None = None

    def register_stored_photo(
        self, *, storage: Any, organization_id: UUID, object_key: str
    ) -> None:
        self.stored_photo = _GrowthDiaryStoredPhoto(storage, organization_id, object_key)

    def prepare_success(
        self,
        *,
        line: Any,
        event: dict,
        line_user_id: str | None,
        organization_id: UUID,
        entry_id: UUID,
        animal_name: str,
        note: str | None,
        has_photo: bool,
        ai_job_id: UUID | None = None,
        legacy_ai: bool = False,
    ) -> None:
        self.post_commit = _GrowthDiaryPostCommit(
            line=line,
            event=event,
            line_user_id=line_user_id,
            organization_id=organization_id,
            entry_id=entry_id,
            animal_name=animal_name,
            note=note,
            has_photo=has_photo,
            ai_job_id=ai_job_id,
            legacy_ai=legacy_ai,
        )

    async def compensate(self) -> None:
        photo = self.stored_photo
        self.stored_photo = None
        if photo is None:
            return
        try:
            await photo.storage.delete(
                scope=ObjectScope(photo.organization_id),
                key=photo.object_key,
            )
        except Exception:
            logger.exception(
                "growth_diary_orphan_cleanup_failed",
                extra={
                    "organization_id": str(photo.organization_id),
                    "webhook_event_id": self.event_id,
                },
            )

    async def finish_after_commit(self) -> None:
        action = self.post_commit
        if action is None:
            await self.compensate()
            return

        self.stored_photo = None
        try:
            await _reply(
                action.line,
                action.event,
                [
                    {
                        **_text(
                            "已記錄毛孩的成長日記！感謝分享 🐾"
                            + (
                                " AI 小幫手正在看看，稍後會再傳訊息給你 🤖"
                                if action.ai_job_id is not None or action.legacy_ai
                                else ""
                            )
                        ),
                        "quickReply": {"items": growth_diary_quick_reply_items()},
                    }
                ],
            )
        except Exception:
            logger.exception(
                "growth_diary_success_reply_failed",
                extra={"webhook_event_id": self.event_id},
            )

        if action.ai_job_id is not None:
            try:
                self.background_tasks.add_task(
                    dispatch_ai_job,
                    action.ai_job_id,
                    action.organization_id,
                )
            except Exception:
                logger.exception(
                    "growth_diary_ai_dispatch_registration_failed",
                    extra={"webhook_event_id": self.event_id},
                )
            return
        if action.line_user_id is None or not action.legacy_ai:
            return
        try:
            self.background_tasks.add_task(
                _run_growth_diary_ai_analysis,
                action.line,
                line_user_id=action.line_user_id,
                organization_id=action.organization_id,
                entry_id=action.entry_id,
                animal_name=action.animal_name,
                note=action.note,
                has_photo=action.has_photo,
            )
        except Exception:
            logger.exception(
                "growth_diary_ai_task_registration_failed",
                extra={"webhook_event_id": self.event_id},
            )


@asynccontextmanager
async def _growth_diary_event_transaction(
    session,
    *,
    event_id: str,
    background_tasks: BackgroundTasks,
):
    boundary = _GrowthDiaryEventBoundary(
        event_id=event_id,
        background_tasks=background_tasks,
    )
    try:
        async with session.begin():
            yield boundary
    except BaseException:
        await boundary.compensate()
        raise
    else:
        await boundary.finish_after_commit()


VOLUNTEER_APPLICATION_COMMAND = "我要報名志工"
WALK_REPORT_COMMAND = "開始散步回報"
# No dedicated Rich Menu tile exists for 毛孩日記 yet — the default menu's
# exact two entries (志工／領養) are locked by
# test_default_menu_offers_volunteer_and_adoption_entries, and switching an
# adopter to their own menu at inquiry-submission time is explicitly
# forbidden until a formal adoption-completed lifecycle exists (see
# test_adoption_inquiry_submission_does_not_switch_to_adopter_menu). A typed
# command, same pattern as VOLUNTEER_APPLICATION_COMMAND/WALK_REPORT_COMMAND,
# is the entry point until one of those lands.
GROWTH_DIARY_COMMAND = "毛孩日記"


def _is_walk_report_command(event: dict) -> bool:
    return (
        event.get("type") == "message"
        and event.get("message", {}).get("type") == "text"
        and event.get("message", {}).get("text", "").strip() == WALK_REPORT_COMMAND
    )


def _is_growth_diary_command(event: dict) -> bool:
    return (
        event.get("type") == "message"
        and event.get("message", {}).get("type") == "text"
        and event.get("message", {}).get("text", "").strip() == GROWTH_DIARY_COMMAND
    )


async def _resolve_context(session, line_user_id: str) -> tuple[UUID, UUID, UUID, str]:
    identity = LineWebhookRepository(session)
    authentication = AuthenticationRepository(session)
    webhook_session = await LineWebhookSessionService(identity, authentication).resolve(
        line_user_id
    )
    membership = await authentication.get_effective_membership(
        webhook_session.user_id, webhook_session.organization_id
    )
    if membership is None:
        raise DomainError("shelter_context_required", "請在 LIFF 明確選擇收容所", 409)
    await set_organization_scope(session, webhook_session.organization_id)
    return (
        webhook_session.user_id,
        webhook_session.organization_id,
        membership.id,
        membership.role,
    )


async def _reply(line: LineMessagingPort, event: dict, messages: list[dict]) -> None:
    reply_token = event.get("replyToken")
    if reply_token:
        await line.reply(reply_token=reply_token, messages=messages)
        return
    if event.get("_push_fallback"):
        line_user_id = event.get("source", {}).get("userId")
        if line_user_id:
            await line.push(to_user_id=line_user_id, messages=messages)


def _text(message: str) -> dict:
    return {"type": "text", "text": message}


def _liff_binding_message() -> str:
    return f"請先開啟 LIFF 完成身分綁定或選擇收容所：https://liff.line.me/{get_settings().liff_id}"


def _adopter_lost_message() -> dict:
    return {
        **_text(
            "不好意思，我不太確定這句話的意思 🐾\n"
            "可以輸入「毛孩日記」查看毛孩日記功能，或透過選單使用「領養媒合」喔。"
        ),
        "quickReply": {"items": growth_diary_quick_reply_items()},
    }


async def _is_adopter_only_line_user(session, line_user_id: str) -> bool:
    binding = await LineWebhookRepository(session).binding(line_user_id)
    if binding is None:
        return False
    memberships = await AuthenticationRepository(session).memberships(binding.user_id)
    return not memberships


def _postback(label: str, data: str, *, display_text: str | None = None) -> dict:
    return {
        "type": "action",
        "action": {
            "type": "postback",
            "label": label[:20],
            "data": data,
            "displayText": display_text or label,
        },
    }


def _action(label: str, data: str, *, display_text: str | None = None) -> dict:
    """Template/Flex postback action (quick replies use `_postback`)."""
    return {
        "type": "postback",
        "label": label[:20],
        "data": data,
        "displayText": display_text or label,
    }


def _line_public_base_url(request: Request) -> str | None:
    configured = get_settings().web_public_base_url.strip().rstrip("/")
    if configured.startswith("https://"):
        return configured
    request_base = str(request.base_url).rstrip("/")
    return request_base if request_base.startswith("https://") else None


async def _animal_photo_url(
    public_base_url: str | None, organization_id: UUID, animal
) -> str | None:
    if not public_base_url or not animal.current_photo_key:
        return None
    token = issue_adoption_photo_token(
        organization_id=organization_id,
        animal_id=animal.id,
        object_key=animal.current_photo_key,
        ttl_seconds=300,
    )
    return f"{public_base_url}/v1/public/adoption/animals/{animal.id}/photo?token={token}"


def _volunteer_application_liff_url() -> str:
    return f"https://liff.line.me/{get_settings().liff_id}"


def _line_role_menu_features_active() -> bool:
    return get_settings().line_role_menu_features_active()


def _rich_menu_router() -> RichMenuRoutingService | None:
    """四個 richMenuId 都沒設定時回 None，選單切換為 no-op。"""
    settings = get_settings()
    if not _line_role_menu_features_active():
        return None
    registry = build_registry(
        default=settings.line_rich_menu_default_id,
        volunteer=settings.line_rich_menu_volunteer_id,
        adopter=settings.line_rich_menu_adopter_id,
        staff=settings.line_rich_menu_staff_id,
    )
    if not registry.menu_ids:
        return None
    return RichMenuRoutingService(LineMessagingApiAdapter(), registry)


async def _switch_rich_menu(line_user_id: str | None, role: str | None) -> bool:
    """把使用者的 Rich Menu 切到指定角色（role=None 為 default）。

    Best-effort：切換失敗不影響回覆本身，只記 log。
    """
    if not line_user_id:
        return False
    router = _rich_menu_router()
    if router is None:
        return False
    try:
        rich_menu_id = await router.link_for_user(line_user_id=line_user_id, role=role)
        return rich_menu_id is not None
    except Exception:
        logger.warning("switching rich menu failed (role=%s)", role, exc_info=True)
        return False


async def _switch_menu_to_default(line_user_id: str | None) -> bool:
    """志工／領養人選單裡的「返回主選單」：切回 default，讓人可以自由換身分入口。"""
    return await _switch_rich_menu(line_user_id, None)


async def _switch_menu_to_volunteer_if_active(session, line_user_id: str | None) -> bool:
    """點「志工服務」時：若已有生效中的志工資格，直接切回志工選單。

    核准通知由 worker 在交易提交後切過一次選單，但「返回主選單」把選單切走之後，
    原本只能靠重新走一次 LIFF 登入／交換身分才能
    切回去——那段路徑（entry 交換）是設計給「還沒決定要去哪個收容所」的人用
    的，已核准的人每次都要重跑一次沒有必要，而且只要中途沒完整跑完
    （沒登入、頁面沒開完、還在 LIFF 內建瀏覽器的快取狀態卡住）選單就切不回去，
    使用者會覺得「按了沒反應」。這裡繞過 LIFF，直接查已核准的 grant 判斷。
    """
    if not line_user_id:
        return False
    identities = AuthenticationRepository(session)
    binding = await identities.get_line_binding(line_user_id)
    if binding is None:
        return False
    memberships = await identities.memberships(binding.user_id, active_only=True)
    for membership in memberships:
        if membership.role != "VOLUNTEER":
            continue
        effective = await identities.lock_effective_volunteer_access(
            binding.user_id, membership.organization_id
        )
        if effective is not None:
            return await _switch_rich_menu(line_user_id, LineRole.VOLUNTEER)
    return False


def _volunteer_application_entry_message() -> dict:
    return {
        "type": "text",
        "text": "請在志工報名頁選擇地區與想服務的收容所。",
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "uri",
                        "label": "開啟志工報名",
                        "uri": _volunteer_application_liff_url(),
                    },
                }
            ]
        },
    }


async def _handle_menu_action(
    line: LineMessagingPort,
    event: dict,
) -> bool:
    """處理角色選單的 postback。

    必須在 _resolve_context 之前跑：選單對所有加好友的人都看得到，包含尚未
    綁定的使用者。而且這些 action 不帶 draft_token，若落到 _handle_postback
    會撞上照護回報草稿的檢查，回覆「缺少回報草稿識別」。
    """
    if event.get("type") != "postback":
        return False
    action = parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True).get(
        "action", [""]
    )[0]
    if not _line_role_menu_features_active() and (
        action in MENU_PLACEHOLDER_ACTIONS
        or action in STAFF_MENU_ACTIONS
        or action
        in {
            "start_binding",
            "start_adoption_matching",
            "back_to_default_menu",
            "open_adoption_hub",
        }
    ):
        await _reply(line, event, [_text("此 LINE 功能目前尚未開放。")])
        return True
    if action == "start_binding":
        # 目前沒有專屬的綁定 LIFF 頁；工作人員綁定走 scripts/bind_line_account.py，
        # 志工走報名流程。實際入口待產品決定後接上。
        await _reply(
            line,
            event,
            [
                _text(
                    "身分綁定功能準備中。若你要報名志工，請點選單的志工報名或輸入「我要報名志工」。"
                )
            ],
        )
        return True
    if action == "start_adoption_matching":
        # 正式領養流程必須在 membership resolution 前由 adoption router 處理。
        return False
    if action == "open_adoption_hub":
        line_user_id = event.get("source", {}).get("userId")
        rich_menu_id = get_settings().line_rich_menu_adoption_hub_id.strip()
        if not line_user_id or not rich_menu_id:
            await _reply(line, event, [_text("領養與日記選單尚未啟用，請聯繫工作人員協助。")])
            return True
        try:
            await line.link_rich_menu(rich_menu_id=rich_menu_id, user_id=line_user_id)
        except Exception:
            logger.warning("switching adoption hub menu failed", exc_info=True)
            await _reply(line, event, [_text("目前無法切換選單，請稍後再試。")])
            return True
        await _reply(line, event, [_text("已切換到領養與毛孩日記選單 🐾")])
        return True
    if action in STAFF_MENU_ACTIONS:
        # Staff action 必須先經過 server-side binding/membership/shelter resolution。
        return False
    if action == "back_to_default_menu":
        # 志工／領養人選單裡的「返回主選單」：讓有個別身份的人可以自由切回去，
        # 重新選志工服務或領養流程，不用退出好友重加。
        line_user_id = event.get("source", {}).get("userId")
        switched = await _switch_menu_to_default(line_user_id)
        if switched:
            await _reply(line, event, [_text("已切回主選單，請重新選擇志工服務或領養流程。")])
        else:
            await _reply(line, event, [_text("選單切換功能尚未啟用，請聯繫工作人員協助。")])
        return True
    placeholder = MENU_PLACEHOLDER_ACTIONS.get(action)
    if placeholder is None:
        return False
    await _reply(line, event, [_text(placeholder)])
    return True


async def _handle_staff_menu_action(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    organization_id: UUID,
    role: str,
) -> bool:
    if event.get("type") != "postback":
        return False
    action = parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True).get(
        "action", [""]
    )[0]
    if action not in STAFF_MENU_ACTIONS:
        return False
    if role not in {LineRole.STAFF, LineRole.SHELTER_ADMIN}:
        raise DomainError("staff_access_required", "需要目前收容所的工作人員權限", 403)
    if action == "staff_animal_list":
        animals = await AnimalRepository(session, organization_id).list_active()
        rows = [
            f"• {animal.name}（{animal.shelter_number or '無收容編號'}）" for animal in animals[:10]
        ]
        suffix = f"\n另有 {len(animals) - 10} 隻，請至管理介面查看。" if len(animals) > 10 else ""
        text = "目前沒有 active 動物。" if not rows else "目前動物：\n" + "\n".join(rows) + suffix
        await _reply(line, event, [_text(text)])
        return True
    if action == "staff_change_status":
        await _reply(
            line, event, [_text("為避免誤改資料，請先在動物清單確認個體，再至管理介面變更狀態。")]
        )
        return True
    if action not in MENU_LIFF_ACTIONS:
        return False
    liff_id = get_settings().line_staff_liff_id.strip()
    if not liff_id:
        await _reply(line, event, [_text("工作人員 LIFF 尚未設定，請聯繫系統管理員。")])
        return True
    uri = f"https://liff.line.me/{liff_id}?{urlencode({'action': action})}"
    await _reply(
        line,
        event,
        [
            {
                "type": "text",
                "text": "已驗證目前收容所權限，請開啟工作人員表單。",
                "quickReply": {
                    "items": [
                        {
                            "type": "action",
                            "action": {"type": "uri", "label": "開啟表單", "uri": uri},
                        }
                    ]
                },
            }
        ],
    )
    return True


async def _handle_public_volunteer_application_entry(
    session,
    line: LineMessagingPort,
    event: dict,
) -> bool:
    is_text_command = (
        event.get("type") == "message"
        and event.get("message", {}).get("type") == "text"
        and event.get("message", {}).get("text", "").strip() == VOLUNTEER_APPLICATION_COMMAND
    )
    postback_values = (
        parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True)
        if event.get("type") == "postback"
        else {}
    )
    is_postback_command = postback_values.get("action", [""])[0] == ("start_volunteer_application")
    if not is_text_command and not is_postback_command:
        return False
    if not _line_role_menu_features_active():
        await _reply(line, event, [_text("此 LINE 功能目前尚未開放。")])
        return True
    line_user_id = event.get("source", {}).get("userId")
    if await _switch_menu_to_volunteer_if_active(session, line_user_id):
        await _reply(
            line,
            event,
            [_text("已切回志工選單，請由下方選單點選「散步回報」。")],
        )
        return True
    await _reply(line, event, [_volunteer_application_entry_message()])
    return True


_ADOPTION_QUESTION_OPTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
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

_ADOPTION_QUESTION_LABEL = {
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
}

_ADOPTION_QUESTION_PROMPT = {
    "housing_type": "你家是什麼樣子呢？🏠",
    "dog_experience": "之前有養狗經驗嗎？🐕",
    "other_pets": "家裡還有其他毛孩嗎？🐱🐶",
    "household_members": "家裡平常有誰在呢？👨‍👩‍👧",
    "work_schedule": "平常的作息大概是？⏰",
    "preferred_size": "想找什麼體型的毛孩呢？📏",
    "preferred_energy": "期待什麼樣的活動力？⚡",
    "parenting_style": "你比較習慣怎麼帶毛孩呢？🧭",
    "patience_level": "如果毛孩不小心搗蛋，你的耐心程度是？🧘",
    "adoption_motivation": "這次想領養毛孩，最主要是為了？💭",
}

_ADOPTION_STATE_QUESTION_KEY = {
    AdoptionDraftState.ANSWERING_PREFERENCE_HOUSING: "housing_type",
    AdoptionDraftState.ANSWERING_PREFERENCE_EXPERIENCE: "dog_experience",
    AdoptionDraftState.ANSWERING_PREFERENCE_OTHER_PETS: "other_pets",
    AdoptionDraftState.ANSWERING_PREFERENCE_HOUSEHOLD: "household_members",
    AdoptionDraftState.ANSWERING_PREFERENCE_SCHEDULE: "work_schedule",
    AdoptionDraftState.ANSWERING_PREFERENCE_PARENTING_STYLE: "parenting_style",
    AdoptionDraftState.ANSWERING_PREFERENCE_PATIENCE: "patience_level",
    AdoptionDraftState.ANSWERING_PREFERENCE_ADOPTION_MOTIVATION: "adoption_motivation",
    AdoptionDraftState.ANSWERING_PREFERENCE_SIZE: "preferred_size",
    AdoptionDraftState.ANSWERING_PREFERENCE_ENERGY: "preferred_energy",
    AdoptionDraftState.ANSWERING_HOUSING: "housing_type",
    AdoptionDraftState.ANSWERING_EXPERIENCE: "dog_experience",
    AdoptionDraftState.ANSWERING_OTHER_PETS: "other_pets",
    AdoptionDraftState.ANSWERING_HOUSEHOLD: "household_members",
    AdoptionDraftState.ANSWERING_SCHEDULE: "work_schedule",
    AdoptionDraftState.ANSWERING_PARENTING_STYLE: "parenting_style",
    AdoptionDraftState.ANSWERING_PATIENCE: "patience_level",
    AdoptionDraftState.ANSWERING_ADOPTION_MOTIVATION: "adoption_motivation",
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
_QUESTION_ORDER = {
    "specific_animal": _BASE_QUESTION_ORDER,
    "recommend_me": _BASE_QUESTION_ORDER + ("preferred_size", "preferred_energy"),
}


def _answer_display(key: str, value: str) -> str:
    for code, emoji, label in _ADOPTION_QUESTION_OPTIONS.get(key, ()):
        if code == value:
            return f"{emoji} {label}"
    return value


def _adoption_answer_validator(key: str, value: str) -> None:
    options = _ADOPTION_QUESTION_OPTIONS.get(key)
    if options is not None and value not in {code for code, _, _ in options}:
        raise DomainError("invalid_answer_value", f"不支援的領養問卷答案：{key}", 422)


async def _get_or_create_adopter_identity(session, line_user_id: str) -> UUID:
    identity = LineWebhookRepository(session)
    binding = await identity.binding(line_user_id)
    if binding is not None:
        return binding.user_id
    user = await identity.add(User(display_name="LINE 領養人", status="active"))
    binding = await identity.add(
        LineUserBinding(line_user_id=line_user_id, user_id=user.id, status="active")
    )
    return binding.user_id


async def _active_adoption_draft(session, line_user_id: str):
    if not _line_role_menu_features_active():
        return None
    binding = await LineWebhookRepository(session).binding(line_user_id)
    if binding is None:
        return None
    await set_authentication_user_scope(session, binding.user_id)
    return await AdoptionDraftRepository(session, None).get_active_for_adopter(binding.user_id)


def _adoption_cancel_item() -> dict:
    return _postback("取消", urlencode({"action": "cancel", "flow": "adoption"}))


async def _reply_adoption_animal_page(
    session, line, event, *, draft, public_base_url, page=1, query=""
):
    if draft.current_step != AdoptionDraftState.SELECTING_TARGET_ANIMAL.value:
        raise DomainError("invalid_browse_step", "請先回到心有所屬的動物清單再搜尋或翻頁。", 409)
    if draft.expires_at <= datetime.now(timezone.utc):
        raise DomainError("draft_expired", "對話已過期，請重新點選領養媒合。", 409)
    query = query.strip()
    if len(query) > 20:
        raise DomainError("invalid_search", "請輸入 20 字以內的名字或收容編號。", 422)
    await set_organization_scope(session, draft.organization_id)
    animals, total = await AnimalRepository(session, draft.organization_id).list_adoptable_page(
        page=page, query=query
    )
    pages = max(1, (total + 11) // 12)
    page = max(1, min(page, pages))
    items = []
    for label, target in (("上一頁", page - 1), ("下一頁", page + 1)):
        if 1 <= target <= pages:
            items.append(
                _postback(
                    label,
                    urlencode(
                        {
                            "action": "browse_animals",
                            "flow": "adoption",
                            "page": target,
                            "query": query,
                        }
                    ),
                )
            )
    if query:
        items.append(_postback("返回全部清單", "action=browse_animals&flow=adoption&page=1"))
    items.extend([_postback("返回領養方式", "action=back&flow=adoption"), _adoption_cancel_item()])
    description = f"共 {total} 隻，第 {page}／{pages} 頁。可輸入名字或收容編號搜尋（最多 20 字）。"
    if not animals:
        description = (
            "找不到符合的動物，請檢查名字或收容編號，或返回全部清單。"
            if query
            else "目前沒有可領養的動物，可返回選擇其他收容所。"
        )
    messages = [_text(description)]
    if animals:
        cards = [
            MatchReportCard(
                animal_id=str(animal.id),
                name=animal.name,
                shelter_number=animal.shelter_number,
                photo_url=await _animal_photo_url(public_base_url, draft.organization_id, animal),
                selectable=True,
                select_action="select_target_animal",
                select_label="選這隻",
            )
            for animal in animals
        ]
        messages.append(build_target_animal_picker(cards))
    messages[-1]["quickReply"] = {"items": items}
    await _reply(line, event, messages)


async def _adoption_reply_for_state(
    session,
    line,
    event: dict,
    *,
    draft,
    public_base_url: str | None,
    lead: list[dict] | None = None,
) -> None:
    state = AdoptionDraftState(draft.current_step)

    def state_action(label: str, action: str, value: str | None = None) -> dict:
        data = {
            "action": action,
            "flow": "adoption",
            "step": draft.current_step,
            "version": draft.interaction_version,
        }
        if value is not None:
            data["value"] = value
        return _action(label, urlencode(data))

    if state == AdoptionDraftState.SELECTING_ORGANIZATION:
        actions = [
            (
                emoji,
                label,
                _action(
                    label,
                    urlencode({"action": "select_region", "flow": "adoption", "value": value}),
                ),
            )
            for value, emoji, label in (
                ("north", "🧭", "北部"),
                ("central", "🌿", "中部"),
                ("south", "☀️", "南部"),
                ("east", "🌊", "東部"),
            )
        ]
        card = build_info_card("請選擇想去的地區 🗺️", accent_index=0, actions=actions)
    elif state == AdoptionDraftState.CHOOSING_PATH:
        card = build_info_card(
            "請選擇領養方式 🐾",
            accent_index=1,
            actions=[
                (
                    "💗",
                    "心有所屬",
                    state_action("心有所屬", "choose_path", "specific_animal"),
                ),
                (
                    "✨",
                    "推薦給我",
                    state_action("推薦給我", "choose_path", "recommend_me"),
                ),
            ],
        )
    elif state == AdoptionDraftState.SELECTING_TARGET_ANIMAL:
        await _reply_adoption_animal_page(
            session, line, event, draft=draft, public_base_url=public_base_url
        )
        return
    elif state == AdoptionDraftState.CONFIRMING_TARGET_ANIMAL:
        animal = await AnimalRepository(session, draft.organization_id).get(draft.target_animal_id)
        if animal is None:
            await _reply(line, event, [_text("動物資料異常，請重新選擇。")])
            return
        card = build_animal_confirm_card(
            name=animal.name,
            shelter_number=animal.shelter_number,
            photo_url=await _animal_photo_url(public_base_url, draft.organization_id, animal),
            confirm_action=state_action("確認是這隻", "confirm_target_animal"),
            back_action=state_action("重新選擇", "back"),
        )
    elif state == AdoptionDraftState.AWAITING_FREETEXT_PROFILE:
        card = build_info_card(
            "跟我們聊聊你的生活狀況吧 🐾",
            accent_index=1,
            body=(
                "請用一段話介紹居住環境、養狗經驗、家庭狀況、平常作息與領養原因。"
                "AI 只會整理你明確提到的內容，不確定的項目仍會逐題確認。"
            ),
            actions=[
                (
                    "☑️",
                    "改為逐題回答",
                    state_action("改為逐題回答", "finish_freetext_profile"),
                )
            ],
        )
    elif state in _ADOPTION_STATE_QUESTION_KEY:
        key = _ADOPTION_STATE_QUESTION_KEY[state]
        order = _QUESTION_ORDER[draft.path]
        card = build_question_card(
            question_key=key,
            interaction_version=draft.interaction_version,
            step=order.index(key) + 1,
            total=len(order),
            prompt=_ADOPTION_QUESTION_PROMPT[key],
            options=[
                QuestionOption(code=code, emoji=emoji, label=label)
                for code, emoji, label in _ADOPTION_QUESTION_OPTIONS[key]
            ],
            accent_index=(order.index(key) % 4),
            back_action=state_action("上一步", "back"),
        )
    elif state == AdoptionDraftState.CONFIRMING_ANSWERS:
        order = _QUESTION_ORDER[draft.path]
        card = build_info_card(
            "請確認你的問卷回答 📋",
            accent_index=2,
            rows=[
                (_ADOPTION_QUESTION_LABEL[key], _answer_display(key, draft.answers.get(key, "")))
                for key in order
            ],
            actions=[
                (
                    "✅",
                    "確認無誤",
                    state_action("確認無誤", "confirm_answers"),
                ),
                ("✏️", "修改", state_action("修改", "back")),
            ],
        )
    elif state == AdoptionDraftState.SELECTING_MATCHED_ANIMAL:
        repository = AnimalRepository(session, draft.organization_id)
        cards = []
        for rank, result in enumerate(draft.match_results or [], start=1):
            animal = await repository.get(UUID(result["animal_id"]))
            if animal is not None:
                cards.append(
                    MatchReportCard(
                        animal_id=str(animal.id),
                        name=animal.name,
                        shelter_number=animal.shelter_number,
                        photo_url=await _animal_photo_url(
                            public_base_url, draft.organization_id, animal
                        ),
                        score=result.get("score"),
                        reasons=tuple(result.get("reasons", [])),
                        rank=rank,
                        selectable=True,
                    )
                )
        if not cards:
            await _reply(line, event, [_text("目前沒有符合條件的可領養動物，請聯繫工作人員協助。")])
            return
        card = build_match_report(cards, max_bubbles=5)
    elif state == AdoptionDraftState.AWAITING_AI_SUITABILITY:
        # Entered right after the questionnaire is confirmed — the AI call
        # runs in the background (see _run_adoption_ai_suitability_analysis)
        # and pushes its own result later; this is just the immediate,
        # synchronous reply, plus whatever it's resumed into mid-wait.
        if draft.ai_followup_target_animal_id is not None:
            card = build_info_card(
                "留下你的期待或特殊需求 🐾",
                accent_index=1,
                body="想要母狗、個性安靜的孩子都可以直接打字告訴我們",
            )
        else:
            card = build_info_card(
                "AI 正在分析適配度 🤖", accent_index=3, body="請稍候幾秒鐘，完成後會馬上通知你"
            )
    elif state == AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS:
        card = build_info_card(
            "AI 正在為你精選毛孩 🤖", accent_index=3, body="請稍候幾秒鐘，完成後會馬上通知你"
        )
    elif state == AdoptionDraftState.SELECTING_ALTERNATIVE_ANIMAL:
        # 心有所屬・AI 適配度 <60% 後的替代名單 — draft.target_animal_id is
        # still the ORIGINALLY chosen animal at this point (only changes once
        # select_alternative_animal fires), so it's the one labelled "維持這隻".
        repository = AnimalRepository(session, draft.organization_id)
        cards = []
        for result in draft.match_results or []:
            animal = await repository.get(UUID(result["animal_id"]))
            if animal is None:
                continue
            is_original = animal.id == draft.target_animal_id
            cards.append(
                MatchReportCard(
                    animal_id=str(animal.id),
                    name=animal.name,
                    shelter_number=animal.shelter_number,
                    photo_url=await _animal_photo_url(
                        public_base_url, draft.organization_id, animal
                    ),
                    reasons=tuple(result.get("reasons", [])),
                    selectable=True,
                    select_action="select_alternative_animal",
                    select_label="維持這隻" if is_original else "換成這隻",
                )
            )
        if not cards:
            await _reply(line, event, [_text("目前沒有可選擇的名單，請聯繫工作人員協助。")])
            return
        card = build_match_report(cards, max_bubbles=5)
    elif state == AdoptionDraftState.CONFIRMING_ALTERNATIVE_ANIMAL:
        animal = await AnimalRepository(session, draft.organization_id).get(draft.target_animal_id)
        if animal is None:
            await _reply(line, event, [_text("動物資料異常，請重新選擇。")])
            return
        card = build_animal_confirm_card(
            name=animal.name,
            shelter_number=animal.shelter_number,
            photo_url=await _animal_photo_url(public_base_url, draft.organization_id, animal),
            confirm_action=state_action("確認是這隻", "confirm_alternative_animal"),
            back_action=state_action("重新選擇", "back"),
        )
    elif state == AdoptionDraftState.AWAITING_ADOPTER_NAME:
        card = build_info_card("請留下您的姓名 🧑‍🤝‍🧑", accent_index=1, body="請直接輸入姓名")
    elif state == AdoptionDraftState.AWAITING_CONTACT_TIME:
        card = build_info_card(
            "方便聯繫的時間是？⏰",
            accent_index=1,
            body="也可以直接輸入",
            actions=[
                (
                    "🌤️",
                    "平日白天",
                    state_action("平日白天", "contact_time", "平日白天（9-18點）"),
                ),
                (
                    "🌙",
                    "平日晚上",
                    state_action("平日晚上", "contact_time", "平日晚上（18-22點）"),
                ),
                (
                    "🌈",
                    "假日皆可",
                    state_action("假日皆可", "contact_time", "假日皆可"),
                ),
            ],
        )
    elif state == AdoptionDraftState.AWAITING_PHONE_NUMBER:
        card = build_info_card("請留下手機號碼 📞", accent_index=1, body="例如 0912345678")
    elif state in CONTACT_EDIT_STATES:
        key = CONTACT_EDIT_STATES[state]
        label = {"adopter_name": "姓名", "contact_time": "聯絡時間", "phone_number": "電話"}[key]
        hint = (
            "請輸入 10 碼手機號碼，例如 0912345678"
            if key == "phone_number"
            else "請直接輸入修改後的內容"
        )
        card = build_info_card(
            f"修改{label}",
            accent_index=1,
            body=f"目前內容：{draft.answers.get(key, '')}\n{hint}",
            actions=[
                (
                    "↩️",
                    "返回摘要",
                    state_action("返回摘要", "cancel_contact_edit"),
                )
            ],
        )
    elif state == AdoptionDraftState.REVIEWING:
        card = build_info_card(
            "領養意願摘要 📋",
            accent_index=2,
            rows=[
                ("姓名", draft.answers.get("adopter_name", "")),
                ("方便聯繫時間", draft.answers.get("contact_time", "")),
                ("聯絡電話", draft.answers.get("phone_number", "")),
            ],
            actions=[
                (
                    "📮",
                    "送出",
                    state_action("送出", "submit"),
                ),
                *[
                    (
                        "✏️",
                        label,
                        state_action(label, "edit_contact", key),
                    )
                    for key, label in (
                        ("adopter_name", "修改姓名"),
                        ("contact_time", "修改聯絡時間"),
                        ("phone_number", "修改電話"),
                    )
                ],
            ],
        )
    else:
        await _reply(line, event, [_text("領養流程狀態已更新，請重新點選「領養流程」。")])
        return
    quick_reply_items = [_adoption_cancel_item()]
    if state == AdoptionDraftState.SELECTING_MATCHED_ANIMAL:
        quick_reply_items.insert(
            0,
            _postback(
                "都不喜歡，看看別的",
                urlencode({"action": "browse_all_animals", "flow": "adoption"}),
            ),
        )
    card["quickReply"] = {"items": quick_reply_items}
    await _reply(line, event, [*(lead or []), card])


def _build_gemini_client(settings) -> GeminiClient | None:
    """None when neither auth mode is configured — callers treat that as
    "skip this background task silently". A service account (Vertex AI)
    takes precedence over a plain API key (AI Studio) when both are set."""
    if settings.gemini_service_account_path:
        return GeminiClient(
            model_name=settings.gemini_model_name,
            service_account_path=settings.gemini_service_account_path,
            location=settings.gemini_vertex_location,
        )
    if settings.gemini_api_key:
        return GeminiClient(model_name=settings.gemini_model_name, api_key=settings.gemini_api_key)
    return None


async def _run_adoption_profile_extraction(
    line,
    *,
    line_user_id: str,
    organization_id: UUID,
    draft_id: UUID,
    text: str,
    public_base_url: str | None,
) -> None:
    """Extract free-text answers without holding a database lock during AI I/O."""
    gemini = _build_gemini_client(get_settings())
    try:
        async with session_factory() as read_session:
            async with read_session.begin():
                await set_organization_scope(read_session, organization_id)
                draft = await AdoptionDraftRepository(read_session, organization_id).get(draft_id)
                if (
                    draft is None
                    or draft.status != "active"
                    or draft.current_step != AdoptionDraftState.AWAITING_FREETEXT_PROFILE.value
                ):
                    return
                adopter_user_id = draft.adopter_user_id
                include_recommend_me_keys = draft.path == AdoptionPath.RECOMMEND_ME.value
        extracted: dict[str, str] = {}
        if gemini is not None:
            async with session_factory() as prompt_session:
                extracted = await AdoptionAiAnalysisService(
                    prompt_session, organization_id, gemini
                ).extract_profile(
                    text=text,
                    include_recommend_me_keys=include_recommend_me_keys,
                )
        else:
            logger.info("adoption_profile_extraction_skipped_no_credentials")

        async with session_factory() as write_session:
            async with write_session.begin():
                await set_organization_scope(write_session, organization_id)
                repository = AdoptionDraftRepository(write_session, organization_id)
                try:
                    result = await LineAdoptionConversationService(
                        repository
                    ).apply_freetext_answers(
                        adopter_user_id=adopter_user_id,
                        extracted=extracted,
                    )
                except DomainError as error:
                    if error.code in {"draft_access_denied", "invalid_state_transition"}:
                        return
                    raise
                updated = await repository.get(draft_id)
                if updated is None:
                    return
                updated_path = updated.path
                updated_answers = dict(updated.answers)
                updated_state = result.state

        order = _QUESTION_ORDER[updated_path]
        summary = build_info_card(
            "AI 已整理問卷內容 🤖",
            accent_index=1,
            body=("已填入你明確提到的項目；標示待確認的內容仍會由系統詢問。"),
            rows=[
                (
                    _ADOPTION_QUESTION_LABEL[key],
                    _answer_display(key, updated_answers[key])
                    if key in updated_answers
                    else "待確認",
                )
                for key in order
            ],
        )
        await line.push(to_user_id=line_user_id, messages=[summary])
        if updated_state == AdoptionDraftState.AWAITING_FREETEXT_PROFILE:
            return
        if result.entered_awaiting_ai_recommendations:
            await _run_adoption_ai_recommendation_curation(
                line,
                line_user_id=line_user_id,
                organization_id=organization_id,
                draft_id=draft_id,
                public_base_url=public_base_url,
            )
            return
        async with session_factory() as render_session:
            async with render_session.begin():
                await set_organization_scope(render_session, organization_id)
                current = await AdoptionDraftRepository(render_session, organization_id).get(
                    draft_id
                )
                if current is not None:
                    await _adoption_reply_for_state(
                        render_session,
                        line,
                        {"source": {"userId": line_user_id}, "_push_fallback": True},
                        draft=current,
                        public_base_url=public_base_url,
                    )
    except Exception:
        logger.exception("adoption_profile_extraction_failed")
    finally:
        if gemini is not None:
            await gemini.aclose()


async def _run_adoption_ai_suitability_analysis(
    line,
    *,
    line_user_id: str,
    organization_id: UUID,
    draft_id: UUID,
    animal_id: UUID,
    public_base_url: str | None,
) -> None:
    """Background task (see `BackgroundTasks` in `webhook()`) — runs AFTER
    the synchronous reply has already been sent, so it opens its own DB
    session rather than reusing the request's (already closed by then).
    Every failure mode (no API key, draft/animal vanished mid-flight, Gemini
    call failed) degrades to silence or a best-effort fallback push rather
    than raising — nothing here can affect the reply the adopter already
    got."""
    settings = get_settings()
    gemini = _build_gemini_client(settings)
    async with session_factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            draft = await AdoptionDraftRepository(session, organization_id).get(draft_id)
            animal = await AnimalRepository(session, organization_id).get(animal_id)
            if (
                draft is None
                or animal is None
                or draft.status != "active"
                or draft.current_step != AdoptionDraftState.AWAITING_AI_SUITABILITY.value
            ):
                # The adopter cancelled, backed out, or otherwise moved on
                # while this was running — nothing left to attach a result to.
                return
            result = (
                await AdoptionAiAnalysisService(
                    session, organization_id, gemini
                ).analyze_suitability(answers=draft.answers, animal=animal)
                if gemini is not None
                else None
            )
            messages: list[dict] = []
            if result is not None:
                draft.ai_suitability_score = result.score
                draft.ai_suitability_explanation = result.explanation
                messages.append(
                    build_ai_suitability_card(
                        AiSuitabilityCard(
                            animal_id=str(animal.id),
                            name=animal.name,
                            shelter_number=animal.shelter_number,
                            photo_url=await _animal_photo_url(
                                public_base_url, organization_id, animal
                            ),
                            score=result.score,
                            explanation=result.explanation,
                        )
                    )
                )
            else:
                if gemini is None:
                    logger.info("adoption_ai_suitability_skipped_no_credentials")
                messages.append(_text("AI 適配度分析暫時無法使用，不過還是可以繼續留下聯絡方式 🐾"))
            # A score under 60 pauses here to ask about special requirements
            # (see _handle_ai_followup_answer) instead of moving on to the
            # adopter-name request — everything else (a good score, or no
            # score at all) proceeds straight there now that AI has had its
            # say.
            if result is not None and result.score < 60:
                draft.ai_followup_target_animal_id = animal.id
                messages.append(
                    _text(
                        "如果不介意，可以告訴我們你對這隻毛孩的期待或特殊需求嗎？"
                        "想要母狗、個性安靜的孩子都可以直接打字告訴我們 🐾"
                    )
                )
            else:
                draft.current_step = AdoptionDraftState.AWAITING_ADOPTER_NAME.value
                messages.append(
                    build_info_card("請留下您的姓名 🧑‍🤝‍🧑", accent_index=1, body="請直接輸入姓名")
                )
    # Push after the transaction above has committed — a push failure here
    # (network, LINE API error) must not roll back the score/state that was
    # just saved.
    messages[-1]["quickReply"] = {"items": [_adoption_cancel_item()]}
    try:
        await line.push(to_user_id=line_user_id, messages=messages)
    except Exception:
        logger.exception("adoption_ai_suitability_push_failed")


async def _run_adoption_ai_followup_recommendations(
    line,
    *,
    line_user_id: str,
    organization_id: UUID,
    draft_id: UUID,
    exclude_animal_id: UUID,
    special_request: str,
    public_base_url: str | None,
) -> None:
    """Background task for the second Gemini call — triggered by
    `_handle_ai_followup_answer` once the adopter answers the "any special
    requirements?" question. The originally-chosen animal is always offered
    back as "維持這隻" alongside whatever AI alternatives come back — the
    adopter must explicitly (re)confirm a target before contact info is
    asked for, whether they stick with the original or switch (see
    SELECTING_ALTERNATIVE_ANIMAL / CONFIRMING_ALTERNATIVE_ANIMAL)."""
    settings = get_settings()
    gemini = _build_gemini_client(settings)
    async with session_factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            draft = await AdoptionDraftRepository(session, organization_id).get(draft_id)
            if draft is None or draft.status != "active":
                return
            original = await AnimalRepository(session, organization_id).get(exclude_animal_id)
            alternatives: list[tuple] = []
            if gemini is not None:
                service = AdoptionAiAnalysisService(session, organization_id, gemini)
                alternatives = (
                    await service.recommend_alternatives(
                        special_request=special_request, exclude_animal_id=exclude_animal_id
                    )
                    or []
                )
            else:
                logger.info("adoption_ai_alternatives_skipped_no_credentials")

            draft.ai_followup_target_animal_id = None
            if original is None and not alternatives:
                # Nothing left to offer a choice between — fall back straight
                # to the adopter-name request, same as the old
                # (pre-selection-step) graceful-degradation behaviour.
                draft.current_step = AdoptionDraftState.AWAITING_ADOPTER_NAME.value
                messages: list[dict] = [
                    _text("這次沒有找到更適合的建議，不過你的申請資料工作人員都收到了 🐾"),
                    build_info_card("請留下您的姓名 🧑‍🤝‍🧑", accent_index=1, body="請直接輸入姓名"),
                ]
            else:
                candidate_ids: list[str] = []
                match_results: list[dict] = []
                cards: list[MatchReportCard] = []
                if original is not None:
                    candidate_ids.append(str(original.id))
                    match_results.append(
                        {"animal_id": str(original.id), "reasons": ["你原本選定的毛孩"]}
                    )
                    cards.append(
                        MatchReportCard(
                            animal_id=str(original.id),
                            name=original.name,
                            shelter_number=original.shelter_number,
                            photo_url=await _animal_photo_url(
                                public_base_url, organization_id, original
                            ),
                            reasons=("你原本選定的毛孩",),
                            selectable=True,
                            select_action="select_alternative_animal",
                            select_label="維持這隻",
                        )
                    )
                for animal, reason in alternatives:
                    candidate_ids.append(str(animal.id))
                    match_results.append({"animal_id": str(animal.id), "reasons": [reason]})
                    cards.append(
                        MatchReportCard(
                            animal_id=str(animal.id),
                            name=animal.name,
                            shelter_number=animal.shelter_number,
                            photo_url=await _animal_photo_url(
                                public_base_url, organization_id, animal
                            ),
                            reasons=(reason,),
                            selectable=True,
                            select_action="select_alternative_animal",
                            select_label="換成這隻",
                        )
                    )
                draft.candidate_match_ids = candidate_ids
                draft.match_results = match_results
                draft.current_step = AdoptionDraftState.SELECTING_ALTERNATIVE_ANIMAL.value
                intro = (
                    "這幾隻毛孩你可以參考看看，也可以維持原本的選擇："
                    if alternatives
                    else "這次沒有找到其他更適合的建議，你原本選擇的毛孩依然是很棒的選擇 🐾"
                )
                messages = [_text(intro), build_match_report(cards, max_bubbles=5)]
            messages[-1]["quickReply"] = {"items": [_adoption_cancel_item()]}
    try:
        await line.push(to_user_id=line_user_id, messages=messages)
    except Exception:
        logger.exception("adoption_ai_alternatives_push_failed")


async def _run_adoption_ai_recommendation_curation(
    line,
    *,
    line_user_id: str,
    organization_id: UUID,
    draft_id: UUID,
    public_base_url: str | None,
) -> None:
    """Background task for 推薦名單's AI reranking — triggered once the
    preference questionnaire is done and a rule-based candidate pool
    (`draft.candidate_match_ids`/`match_results`, up to 5) has already been
    computed synchronously. Degrades to that rule-based pool, unscored, if
    Gemini is unavailable or fails — the adopter still gets a list."""
    settings = get_settings()
    gemini = _build_gemini_client(settings)
    async with session_factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            draft = await AdoptionDraftRepository(session, organization_id).get(draft_id)
            if (
                draft is None
                or draft.status != "active"
                or draft.current_step != AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS.value
            ):
                return
            repository = AnimalRepository(session, organization_id)
            candidates = [
                animal
                for animal in [
                    await repository.get(UUID(result["animal_id"]))
                    for result in draft.match_results or []
                ]
                if animal is not None
            ]
            if not candidates:
                messages: list[dict] = [_text("目前沒有符合條件的可領養動物，請聯繫工作人員協助。")]
            else:
                curated: list[tuple] | None = None
                if gemini is not None:
                    curated = await AdoptionAiAnalysisService(
                        session, organization_id, gemini
                    ).curate_recommendations(answers=draft.answers, candidates=candidates)
                else:
                    logger.info("adoption_ai_recommendation_curation_skipped_no_credentials")
                if curated:
                    draft.candidate_match_ids = [str(animal.id) for animal, _, _ in curated]
                    draft.match_results = [
                        {"animal_id": str(animal.id), "score": score, "reasons": [explanation]}
                        for animal, score, explanation in curated
                    ]
                    cards = [
                        MatchReportCard(
                            animal_id=str(animal.id),
                            name=animal.name,
                            shelter_number=animal.shelter_number,
                            photo_url=await _animal_photo_url(
                                public_base_url, organization_id, animal
                            ),
                            score=score,
                            reasons=(explanation,),
                            rank=rank,
                            selectable=True,
                        )
                        for rank, (animal, score, explanation) in enumerate(curated, start=1)
                    ]
                    intro = f"🤖 AI 幫你精選了 {len(cards)} 隻適合的毛孩："
                else:
                    # No Gemini, or the call failed/returned nothing usable —
                    # fall back to the rule-based pool already sitting in
                    # match_results, unscored (its raw rule score isn't a
                    # percentage a Flex card should show as one).
                    draft.match_results = [
                        {"animal_id": str(animal.id), "reasons": []} for animal in candidates
                    ]
                    cards = [
                        MatchReportCard(
                            animal_id=str(animal.id),
                            name=animal.name,
                            shelter_number=animal.shelter_number,
                            photo_url=await _animal_photo_url(
                                public_base_url, organization_id, animal
                            ),
                            rank=rank,
                            selectable=True,
                        )
                        for rank, animal in enumerate(candidates[:3], start=1)
                    ]
                    intro = "為你推薦以下毛孩，請選擇一隻："
                messages = [_text(intro), build_match_report(cards, max_bubbles=5)]
            draft.current_step = AdoptionDraftState.SELECTING_MATCHED_ANIMAL.value
            messages[-1]["quickReply"] = {
                "items": [
                    _postback(
                        "都不喜歡，看看別的",
                        urlencode({"action": "browse_all_animals", "flow": "adoption"}),
                    ),
                    _adoption_cancel_item(),
                ]
            }
    try:
        await line.push(to_user_id=line_user_id, messages=messages)
    except Exception:
        logger.exception("adoption_ai_recommendation_push_failed")


async def _resolve_growth_diary_pending(
    session, line_user_id: str
) -> tuple[UUID, GrowthDiaryDraft] | None:
    """Peek-first, mirroring `_active_adoption_draft`: returns None for any
    LINE user with no binding or no pending diary entry, so every other flow
    (adoption, volunteer) falls through completely unaffected. Sets
    authentication-user scope on a hit — growth_diary_drafts/entries and
    adoption_inquiries all carry an owner-or-tenant RLS policy (see
    0041_growth_diary) precisely so this adopter-scoped, cross-shelter peek
    works before any specific organization is known."""
    binding = await LineWebhookRepository(session).binding(line_user_id)
    if binding is None:
        return None
    await set_authentication_user_scope(session, binding.user_id)
    draft = await get_pending_growth_diary_draft(session, binding.user_id)
    if draft is None:
        return None
    return binding.user_id, draft


async def _reply_growth_diary_entry_choice(
    session, line, event: dict, *, adopter_user_id: UUID
) -> None:
    """Tapping the Rich Menu's "毛孩日記" tile (or typing the
    GROWTH_DIARY_COMMAND text shortcut — no dedicated tile exists yet
    without a formal adoption-completed lifecycle to key an adopter-only
    Rich Menu switch off; see test_adoption_inquiry_submission_does_not_
    switch_to_adopter_menu) lands here first — a choice between writing a
    new entry and reviewing past ones, not straight into the share flow
    (回顧 lives one level under this choice, not beside it)."""
    inquiries = await list_inquiries_for_adopter(session, adopter_user_id)
    if not inquiries:
        await _reply(
            line, event, [_text("目前還沒有透過領養媒合完成的領養紀錄，請先完成領養流程。")]
        )
        return
    card = build_info_card(
        "毛孩日記 📔",
        accent_index=1,
        body="想寫新的一篇，還是回顧之前的紀錄呢？",
        actions=[
            (
                "📝",
                "寫新的一篇",
                _action(
                    "寫新的一篇",
                    urlencode({"action": "start_growth_diary_entry", "flow": "growth_diary"}),
                ),
            ),
            (
                "📖",
                "日記回顧",
                _action(
                    "日記回顧",
                    urlencode({"action": "view_growth_diary_history", "flow": "growth_diary"}),
                ),
            ),
        ],
    )
    await _reply(line, event, [card])


async def _handle_growth_diary_postback(
    session,
    line,
    event: dict,
    *,
    adopter_user_id: UUID,
    pending_draft: GrowthDiaryDraft | None,
    public_base_url: str | None,
) -> None:
    values = parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True)
    action = values.get("action", [""])[0]
    value = values.get("value", [None])[0]

    if action == "start_growth_diary":
        await _reply_growth_diary_entry_choice(
            session, line, event, adopter_user_id=adopter_user_id
        )
        return

    if action == "start_growth_diary_entry":
        inquiries = await list_inquiries_for_adopter(session, adopter_user_id)
        if not inquiries:
            await _reply(
                line, event, [_text("目前還沒有透過領養媒合完成的領養紀錄，請先完成領養流程。")]
            )
            return
        if len(inquiries) == 1:
            await _start_growth_diary_entry(session, line, event, adopter_user_id, inquiries[0])
            return
        options = [
            AdoptedAnimalOption(
                inquiry_id=str(inquiry.id),
                animal_name=inquiry.animal_name_snapshot,
                shelter_number=inquiry.shelter_number_snapshot,
            )
            for inquiry in inquiries
        ]
        await _reply(line, event, [build_animal_picker(options)])
        return

    if action == "select_growth_diary_animal":
        inquiry_id = _uuid_value(value or "")
        inquiries = await list_inquiries_for_adopter(session, adopter_user_id)
        inquiry = next((item for item in inquiries if item.id == inquiry_id), None)
        if inquiry is None:
            raise DomainError("inquiry_not_found", "找不到這筆領養紀錄", 404)
        await _start_growth_diary_entry(session, line, event, adopter_user_id, inquiry)
        return

    if action == "view_growth_diary_history":
        await _reply_growth_diary_history(
            session,
            line,
            event,
            adopter_user_id=adopter_user_id,
            public_base_url=public_base_url,
        )
        return

    if action == "snooze_growth_diary_reminder":
        # Pushes the reminder cadence clock forward without starting a
        # pending draft — the adopter just isn't ready to share right now.
        inquiry_id = _uuid_value(value or "")
        inquiries = await list_inquiries_for_adopter(session, adopter_user_id)
        inquiry = next((item for item in inquiries if item.id == inquiry_id), None)
        if inquiry is None:
            raise DomainError("inquiry_not_found", "找不到這筆領養紀錄", 404)
        inquiry.last_growth_diary_prompted_at = datetime.now(timezone.utc)
        await _reply(line, event, [_text("好的，我們晚點再提醒你 🐾")])
        return

    raise DomainError("invalid_postback_action", "目前步驟不允許此操作", 409)


async def _reply_growth_diary_history(
    session,
    line,
    event: dict,
    *,
    adopter_user_id: UUID,
    public_base_url: str | None,
) -> None:
    """毛孩日記回顧 — read-only across every shelter this adopter has ever
    adopted through (like `list_inquiries_for_adopter`), never touches
    pending-draft or reminder-cadence state."""
    inquiries = await list_inquiries_for_adopter(session, adopter_user_id)
    entries = await list_entries_for_inquiries(session, [inquiry.id for inquiry in inquiries])
    if not entries:
        await _reply(
            line,
            event,
            [_text("目前還沒有任何毛孩日記紀錄，快去跟毛孩互動然後回來分享第一篇吧 🐾")],
        )
        return
    inquiries_by_id = {inquiry.id: inquiry for inquiry in inquiries}
    history_entries: list[GrowthDiaryHistoryEntry] = []
    for entry in entries:
        inquiry = inquiries_by_id.get(entry.inquiry_id)
        photo_keys = list(
            entry.photo_keys or ([] if entry.photo_key is None else [entry.photo_key])
        )
        photo_url = None
        if photo_keys and public_base_url:
            token = issue_growth_diary_photo_token(
                organization_id=entry.organization_id,
                entry_id=entry.id,
                object_key=photo_keys[-1],
            )
            photo_url = (
                f"{public_base_url}/v1/public/growth-diary/entries/{entry.id}/photo?token={token}"
            )
        history_entries.append(
            GrowthDiaryHistoryEntry(
                date_label=entry.created_at.strftime("%m/%d"),
                animal_name=inquiry.animal_name_snapshot if inquiry is not None else "毛孩",
                kind="photo" if photo_keys else "text",
                note=entry.note,
                mood=entry.ai_mood,
                reply=entry.ai_reply,
                photo_url=photo_url,
            )
        )
    await _reply(
        line,
        event,
        [
            _text("這是毛孩的成長日記回顧，由新到舊："),
            build_growth_diary_history_carousel(history_entries),
        ],
    )


async def _start_growth_diary_entry(session, line, event, adopter_user_id: UUID, inquiry) -> None:
    await set_pending_growth_diary_draft(
        session,
        adopter_user_id=adopter_user_id,
        organization_id=inquiry.organization_id,
        inquiry_id=inquiry.id,
        animal_id=inquiry.target_animal_id,
    )
    await _reply(
        line,
        event,
        [
            _text(
                f"請直接傳一張照片，或用文字描述「{inquiry.animal_name_snapshot}」"
                "最近的成長狀況（例如體重、活動力、趣事）。輸入「取消」可以取消這次紀錄。"
            )
        ],
    )


async def _organization_today(session, organization_id: UUID) -> date:
    organization = await session.get(Organization, organization_id)
    timezone_name = organization.timezone if organization is not None else "UTC"
    try:
        timezone_info = ZoneInfo(timezone_name)
    except Exception:
        logger.warning(
            "invalid organization timezone; using UTC",
            extra={"organization_id": str(organization_id)},
        )
        timezone_info = timezone.utc
    return datetime.now(timezone_info).date()


async def _handle_growth_diary_message(
    session,
    line,
    event: dict,
    *,
    adopter_user_id: UUID,
    pending_draft: GrowthDiaryDraft,
    event_boundary: _GrowthDiaryEventBoundary,
) -> None:
    message = event.get("message", {})
    message_type = message.get("type")

    if message_type == "text" and message.get("text", "").strip() == "取消":
        await clear_pending_growth_diary_draft(session, adopter_user_id)
        await _reply(line, event, [_text("已取消這次成長日記紀錄。")])
        return

    photo_key: str | None = None
    photo_content_type: str | None = None
    note: str | None = None
    if message_type == "image":
        try:
            content = await line.get_image_content(message_id=message["id"])
            photo_key = (
                f"growth-diary/{pending_draft.inquiry_id}/{event.get('webhookEventId', '')}.media"
            )
            storage = MinioStorageAdapter()
            stored = await MediaProcessingService(storage).store_cleaned(
                organization_id=pending_draft.organization_id,
                object_key=photo_key,
                data=content.content,
                declared_content_type=content.content_type,
                output_policy="growth_diary_webp",
            )
            photo_content_type = stored.metadata.content_type
            event_boundary.register_stored_photo(
                storage=storage,
                organization_id=pending_draft.organization_id,
                object_key=stored.key,
            )
        except Exception:
            await _reply(line, event, [_text("照片處理失敗，請重新傳送一次，或改用文字記錄。")])
            return
    elif message_type == "text":
        note = message.get("text", "").strip()
        if not note:
            await _reply(line, event, [_text("請傳一張照片，或輸入文字記錄成長狀況。")])
            return
    else:
        await _reply(line, event, [_text("請直接傳照片或輸入文字記錄成長日記。")])
        return

    today = await _organization_today(session, pending_draft.organization_id)
    repository = GrowthDiaryRepository(session, pending_draft.organization_id)
    if pending_draft.current_entry_id is not None and pending_draft.entry_date == today:
        entry = await repository.append_to_entry(
            pending_draft.current_entry_id,
            inquiry_id=pending_draft.inquiry_id,
            animal_id=pending_draft.animal_id,
            adopter_user_id=adopter_user_id,
            photo_key=photo_key,
            photo_content_type=photo_content_type,
            note=note,
        )
    else:
        entry = await repository.add_entry(
            inquiry_id=pending_draft.inquiry_id,
            animal_id=pending_draft.animal_id,
            adopter_user_id=adopter_user_id,
            photo_key=photo_key,
            photo_content_type=photo_content_type,
            note=note,
            entry_date=today,
        )
        pending_draft.current_entry_id = entry.id
        pending_draft.entry_date = today
    configured = bool(get_settings().gemini_service_account_path or get_settings().gemini_api_key)
    settings = get_settings()
    celery_enabled = settings.celery_ai_enabled
    local_legacy = (
        configured
        and not celery_enabled
        and settings.app_env.strip().lower() in {"local", "test", "testing"}
    )
    ai_job_id: UUID | None = None
    if celery_enabled:
        entry.ai_analysis_status = "pending"
        photo_keys = list(
            entry.photo_keys or ([] if entry.photo_key is None else [entry.photo_key])
        )
        ai_job = await create_growth_diary_analysis_job(
            AIJobRepository(session, pending_draft.organization_id),
            entry_id=entry.id,
            content_version=entry.content_version,
            photo_keys=photo_keys,
        )
        ai_job_id = ai_job.id
    elif local_legacy:
        entry.ai_analysis_status = "pending"
    else:
        entry.ai_analysis_status = "unconfigured"
        entry.ai_analyzed_at = datetime.now(timezone.utc)
    # Sharing (whether self-initiated or reminder-triggered) resets the
    # reminder cadence clock, so a scheduled nudge never fires right after
    # the adopter just shared on their own.
    inquiry = await AdoptionInquiryRepository(session, pending_draft.organization_id).get(
        pending_draft.inquiry_id
    )
    if inquiry is not None:
        inquiry.last_growth_diary_prompted_at = datetime.now(timezone.utc)
    line_user_id = event.get("source", {}).get("userId")
    event_boundary.prepare_success(
        line=line,
        event=event,
        line_user_id=line_user_id,
        organization_id=pending_draft.organization_id,
        entry_id=entry.id,
        animal_name=inquiry.animal_name_snapshot if inquiry is not None else "毛孩",
        note=note,
        has_photo=photo_key is not None,
        ai_job_id=ai_job_id,
        legacy_ai=local_legacy,
    )


async def _run_growth_diary_ai_analysis(
    line,
    *,
    line_user_id: str,
    organization_id: UUID,
    entry_id: UUID,
    animal_name: str,
    note: str | None,
    has_photo: bool,
) -> None:
    """Analyze the latest entry version without holding a DB lock during AI I/O."""
    settings = get_settings()
    gemini = _build_gemini_client(settings)
    reply_message: dict | None = None
    staff_message: dict | None = None
    staff_line_user_ids: list[str] = []
    try:
        async with session_factory() as claim_session:
            async with claim_session.begin():
                await set_organization_scope(claim_session, organization_id)
                claimed = await claim_session.execute(
                    select(GrowthDiaryEntry)
                    .where(
                        GrowthDiaryEntry.id == entry_id,
                        GrowthDiaryEntry.organization_id == organization_id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                entry = claimed.scalar_one_or_none()
                if entry is None:
                    return
                claimed_version = entry.content_version
                if entry.ai_content_version == claimed_version and entry.ai_analysis_status in {
                    "processing",
                    "succeeded",
                }:
                    return
                entry.ai_content_version = claimed_version
                entry.ai_analysis_status = "processing"
                current_note = entry.note
                photo_keys = list(
                    entry.photo_keys or ([] if entry.photo_key is None else [entry.photo_key])
                )

        photo: bytes | None = None
        photo_mime_type: str | None = None
        if photo_keys:
            try:
                photo, photo_mime_type = await MinioStorageAdapter().get_with_content_type(
                    scope=ObjectScope(organization_id), key=photo_keys[-1]
                )
            except Exception:
                logger.exception("growth_diary_photo_fetch_for_ai_failed")

        result = None
        if gemini is not None and (current_note or photo is not None):
            result = await GrowthDiaryAiAnalysisService(gemini).analyze_entry(
                animal_name=animal_name,
                note=current_note,
                photo=photo,
                photo_mime_type=photo_mime_type,
            )
        elif gemini is None:
            logger.info("growth_diary_ai_analysis_skipped_no_credentials")

        async with session_factory() as write_session:
            async with write_session.begin():
                await set_organization_scope(write_session, organization_id)
                current_result = await write_session.execute(
                    select(GrowthDiaryEntry)
                    .where(
                        GrowthDiaryEntry.id == entry_id,
                        GrowthDiaryEntry.organization_id == organization_id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                entry = current_result.scalar_one_or_none()
                if entry is None or entry.content_version != claimed_version:
                    return
                entry.ai_analyzed_at = datetime.now(timezone.utc)
                if result is None:
                    entry.ai_analysis_status = "unconfigured" if gemini is None else "failed"
                else:
                    entry.ai_analysis_status = "succeeded"
                    entry.ai_mood = result.mood
                    entry.ai_reply = result.adopter_reply
                    entry.ai_staff_summary = result.staff_summary
                    entry.ai_provider = result.provider
                    entry.ai_model_name = result.model_name
                    entry.ai_model_version = result.model_version
                    entry.ai_prompt_version = result.prompt_version
                    entry.ai_output_schema_version = result.output_schema_version
                    entry.ai_raw_output = result.raw_output
                    reply_message = build_growth_diary_ai_reply_card(
                        mood=result.mood, reply_text=result.adopter_reply
                    )
                    if result.mood == "concern":
                        staff_line_user_ids = await GrowthDiaryRepository(
                            write_session, organization_id
                        ).list_staff_line_user_ids()
                        staff_message = _text(
                            "⚠️ 毛孩日記異常通知\n"
                            f"{animal_name} 的領養者剛回報疑似健康狀況異常：\n"
                            f"「{result.staff_summary}」\n"
                            "請儘快確認並視需要主動聯繫領養者。"
                        )
        if result is None and photo_keys:
            reply_message = _text(f"謝謝分享{animal_name}的照片！看到牠現在的樣子真替你們開心 🥰")
        if reply_message is not None:
            reply_message["quickReply"] = {"items": growth_diary_quick_reply_items()}
    except Exception:
        logger.exception("growth_diary_ai_analysis_failed")
        return
    finally:
        if gemini is not None:
            close = getattr(gemini, "aclose", None)
            if close is not None:
                await close()
    if reply_message is not None:
        try:
            await line.push(to_user_id=line_user_id, messages=[reply_message])
        except Exception:
            logger.exception("growth_diary_ai_reply_push_failed")
    if staff_message is not None:
        for staff_line_user_id in staff_line_user_ids:
            try:
                await line.push(to_user_id=staff_line_user_id, messages=[staff_message])
            except Exception:
                logger.exception("growth_diary_staff_alert_push_failed")


async def _handle_adoption_start(
    session, line, event: dict, line_user_id: str, *, public_base_url: str | None
) -> None:
    adopter_user_id = await _get_or_create_adopter_identity(session, line_user_id)
    await set_authentication_user_scope(session, adopter_user_id)
    repository = AdoptionDraftRepository(session, None)
    draft = await repository.lock_active_for_adopter(adopter_user_id)
    repaired_missing_key = None
    if draft is None:
        draft, _ = await LineAdoptionDraftService(
            repository, ttl_seconds=get_settings().draft_ttl_seconds
        ).create(adopter_user_id=adopter_user_id)
    elif draft.organization_id is not None:
        await set_organization_scope(session, draft.organization_id)
        machine = AdoptionDraftStateMachine(
            state=AdoptionDraftState(draft.current_step),
            path=AdoptionPath(draft.path) if draft.path else None,
            answers=AdoptionDraftAnswers(dict(draft.answers)),
            reconfirmation_keys=set(draft.reconfirmation_keys or []),
            freetext_profile_rounds=draft.freetext_profile_rounds or 0,
        )
        repaired_missing_key = machine.repair_for_resume()
        if repaired_missing_key is not None:
            draft.current_step = machine.state.value
            draft.reconfirmation_keys = sorted(machine.reconfirmation_keys)
            draft.interaction_version += 1
            await session.flush()
    await _adoption_reply_for_state(
        session,
        line,
        event,
        draft=draft,
        public_base_url=public_base_url,
        lead=(
            [_text("先前的問卷還有題目未完成，其他答案已保留，請從這題繼續。")]
            if repaired_missing_key is not None
            else None
        ),
    )


async def _handle_adoption_postback(
    session,
    line,
    event: dict,
    *,
    draft,
    public_base_url: str | None,
    background_tasks: BackgroundTasks,
) -> None:
    values = parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True)
    action = values.get("action", [""])[0]
    value = values.get("value", [None])[0]
    adopter_user_id = draft.adopter_user_id

    if action == "back" and (
        values.get("step", [None])[0] is None or values.get("version", [None])[0] is None
    ):
        await _adoption_reply_for_state(
            session, line, event, draft=draft, public_base_url=public_base_url
        )
        return

    if action == "answer":
        state = AdoptionDraftState(draft.current_step)
        current_question = _ADOPTION_STATE_QUESTION_KEY.get(state)
        card_question = values.get("question", [None])[0]
        if current_question is None or card_question != current_question:
            await _adoption_reply_for_state(
                session,
                line,
                event,
                draft=draft,
                public_base_url=public_base_url,
            )
            return

    if action == "browse_animals":
        try:
            page = int(values.get("page", ["1"])[0])
        except ValueError as exc:
            raise DomainError("invalid_page", "請使用清單上的翻頁按鈕。", 422) from exc
        if not 1 <= page <= 10000:
            raise DomainError("invalid_page", "請使用清單上的翻頁按鈕。", 422)
        await _reply_adoption_animal_page(
            session,
            line,
            event,
            draft=draft,
            public_base_url=public_base_url,
            page=page,
            query=values.get("query", [""])[0],
        )
        return

    if action == "browse_all_animals":
        if (
            draft.path != AdoptionPath.RECOMMEND_ME.value
            or draft.current_step != AdoptionDraftState.SELECTING_MATCHED_ANIMAL.value
            or draft.organization_id is None
        ):
            raise DomainError("invalid_browse_step", "請先完成推薦問卷再瀏覽其他毛孩。", 409)
        await set_organization_scope(session, draft.organization_id)
        animals, _total = await AnimalRepository(
            session, draft.organization_id
        ).list_adoptable_page(page=1, limit=12)
        cards = [
            MatchReportCard(
                animal_id=str(animal.id),
                name=animal.name,
                shelter_number=animal.shelter_number,
                photo_url=await _animal_photo_url(public_base_url, draft.organization_id, animal),
                selectable=True,
                select_action="select_target_animal",
                select_label="選這隻",
            )
            for animal in animals
        ]
        if not cards:
            await _reply(line, event, [_text("目前沒有可領養的動物，請聯繫工作人員協助。")])
            return
        picker = build_target_animal_picker(cards)
        picker["quickReply"] = {"items": [_adoption_cancel_item()]}
        await _reply(line, event, [picker])
        return

    if action == "select_region":
        if not value:
            raise DomainError("region_required", "需要選擇地區", 422)
        organizations = await OrganizationRepository(session).list_with_adoptable_animals_by_region(
            value
        )
        await set_authentication_user_scope(session, adopter_user_id)
        if not organizations:
            await _reply(line, event, [_text("這個地區目前沒有開放領養媒合的收容所。")])
            return
        await _reply(
            line,
            event,
            [
                build_shelter_carousel(
                    [
                        ShelterCard(
                            str(organization.id),
                            organization.name,
                            organization.service_area,
                            count,
                            value,
                        )
                        for organization, count in organizations
                    ]
                )
            ],
        )
        return

    if action == "select_organization":
        try:
            candidate_id = UUID(value or "")
        except ValueError as exc:
            raise DomainError("organization_id_required", "需要選擇收容所", 422) from exc
        allowed = {
            item.id for item in await OrganizationRepository(session).list_with_adoptable_animals()
        }
        await set_authentication_user_scope(session, adopter_user_id)
        if candidate_id not in allowed:
            raise DomainError("organization_not_available", "該收容所目前無法領養媒合", 404)
    elif draft.organization_id is not None and not (
        action == "back" and draft.current_step == AdoptionDraftState.CHOOSING_PATH.value
    ):
        await set_organization_scope(session, draft.organization_id)
    else:
        await set_authentication_user_scope(session, adopter_user_id)

    repository = AdoptionDraftRepository(session, draft.organization_id)
    raw_version = values.get("version", [None])[0]
    try:
        expected_version = int(raw_version) if raw_version is not None else None
    except ValueError:
        expected_version = -1
    try:
        result = await LineAdoptionConversationService(
            repository,
            organization_validator=(lambda candidate_id: _true_async(candidate_id)),
            answer_validator=_adoption_answer_validator,
            match_top_n=5,
        ).handle(
            token=None,
            adopter_user_id=adopter_user_id,
            action=action,
            value=value,
            event_id=event.get("webhookEventId", ""),
            expected_question=values.get("question", [None])[0],
            expected_state=values.get("step", [None])[0],
            expected_version=expected_version,
        )
    except DomainError as error:
        if error.code != "stale_adoption_action":
            raise
        await set_authentication_user_scope(session, adopter_user_id)
        current = await AdoptionDraftRepository(session, None).get_active_for_adopter(
            adopter_user_id
        )
        if current is None:
            raise
        if current.organization_id is not None:
            await set_organization_scope(session, current.organization_id)
        await _adoption_reply_for_state(
            session, line, event, draft=current, public_base_url=public_base_url
        )
        return
    if result.inquiry_id is not None:
        await _reply(
            line,
            event,
            [
                build_info_card(
                    "已收到你的領養意願 🎉", accent_index=1, body="收容所工作人員將盡快與你聯絡。"
                )
            ],
        )
        return
    if result.state in {AdoptionDraftState.CANCELLED, AdoptionDraftState.EXPIRED}:
        await _reply(line, event, [build_info_card("已取消這次領養媒合對話", accent_index=3)])
        return
    await set_authentication_user_scope(session, adopter_user_id)
    updated = await AdoptionDraftRepository(session, None).get_active_for_adopter(adopter_user_id)
    if updated is not None:
        if updated.organization_id is not None:
            await set_organization_scope(session, updated.organization_id)
        # AI suitability analysis is scoped to 心有所屬 only for now — the
        # extra checks are cheap insurance against a future graph change
        # silently over-firing this.
        line_user_id = event.get("source", {}).get("userId")
        if result.ai_job_id is not None and updated.organization_id is not None:
            background_tasks.add_task(
                dispatch_ai_job,
                result.ai_job_id,
                updated.organization_id,
            )
        elif (
            result.entered_awaiting_ai_suitability
            and get_settings().app_env.strip().lower() in {"local", "test", "testing"}
            and updated.path == "specific_animal"
            and updated.organization_id is not None
            and updated.target_animal_id is not None
            and line_user_id
        ):
            # Rollout fallback: preserve the proven in-process path until the
            # Celery worker is explicitly enabled for this environment.
            background_tasks.add_task(
                _run_adoption_ai_suitability_analysis,
                line,
                line_user_id=line_user_id,
                organization_id=updated.organization_id,
                draft_id=updated.id,
                animal_id=updated.target_animal_id,
                public_base_url=public_base_url,
            )
        # Same idea, for 推薦名單's AI-curated recommendation list.
        if (
            result.entered_awaiting_ai_recommendations
            and result.ai_job_id is None
            and get_settings().app_env.strip().lower() in {"local", "test", "testing"}
            and updated.path == "recommend_me"
            and updated.organization_id is not None
            and line_user_id
        ):
            background_tasks.add_task(
                _run_adoption_ai_recommendation_curation,
                line,
                line_user_id=line_user_id,
                organization_id=updated.organization_id,
                draft_id=updated.id,
                public_base_url=public_base_url,
            )
        await _adoption_reply_for_state(
            session,
            line,
            event,
            draft=updated,
            public_base_url=public_base_url,
            lead=(
                [_text("剛剛的問卷還有一題需要補填，其他答案已為你保留。")]
                if result.repaired_missing_key is not None
                else None
            ),
        )


async def _true_async(_value) -> bool:
    return True


async def _handle_adoption_text(
    session,
    line,
    event: dict,
    *,
    draft,
    text: str,
    public_base_url: str | None,
    background_tasks: BackgroundTasks,
) -> None:
    if draft.organization_id is not None:
        await set_organization_scope(session, draft.organization_id)
    repository = AdoptionDraftRepository(session, draft.organization_id)
    if draft.current_step == AdoptionDraftState.AWAITING_FREETEXT_PROFILE.value:
        stripped = text.strip()
        if not stripped:
            await _reply(line, event, [_text("請直接打字介紹你的生活狀況，或選擇逐題回答。")])
            return
        if len(stripped) > 2000:
            raise DomainError(
                "invalid_adoption_profile_text",
                "請輸入 1 至 2000 字的生活狀況介紹",
                422,
            )
        settings = get_settings()
        line_user_id = event.get("source", {}).get("userId")
        if settings.celery_ai_enabled and draft.organization_id is not None:
            result = await LineAdoptionConversationService(repository).submit_freetext_profile(
                adopter_user_id=draft.adopter_user_id,
                profile_text=stripped,
            )
            assert result.ai_job_id is not None
            background_tasks.add_task(
                dispatch_ai_job,
                result.ai_job_id,
                draft.organization_id,
            )
            await _reply(line, event, [_text("收到了，正在整理問卷內容；完成後會通知你 🤖")])
            return
        if settings.app_env.strip().lower() not in {"local", "test", "testing"}:
            await LineAdoptionConversationService(repository).handle(
                token=None,
                adopter_user_id=draft.adopter_user_id,
                action="finish_freetext_profile",
                value=None,
                event_id=event.get("webhookEventId", ""),
            )
            updated = await repository.get(draft.id)
            if updated is not None:
                await _adoption_reply_for_state(
                    session,
                    line,
                    event,
                    draft=updated,
                    public_base_url=public_base_url,
                    lead=[_text("AI 整理目前未啟用，已改為逐題回答。")],
                )
            return
        if line_user_id and draft.organization_id is not None:
            background_tasks.add_task(
                _run_adoption_profile_extraction,
                line,
                line_user_id=line_user_id,
                organization_id=draft.organization_id,
                draft_id=draft.id,
                text=stripped,
                public_base_url=public_base_url,
            )
        await _reply(line, event, [_text("收到了，正在整理問卷內容；完成後會通知你 🤖")])
        return
    if draft.current_step == AdoptionDraftState.AWAITING_AI_SUITABILITY.value:
        # No phone number/name is accepted yet at this step — the contact
        # info ask waits for the AI result. Any text here is either the
        # answer to the AI's low-score follow-up question, or (if that
        # hasn't arrived yet) just a stray message to gently defer.
        if draft.ai_followup_target_animal_id is not None:
            special_request = text.strip()
            if not special_request or len(special_request) > 2000:
                raise DomainError(
                    "invalid_adoption_special_request",
                    "請輸入 1 至 2000 字的特殊需求",
                    422,
                )
            settings = get_settings()
            if settings.celery_ai_enabled and draft.organization_id is not None:
                result = await LineAdoptionConversationService(repository).submit_followup_request(
                    adopter_user_id=draft.adopter_user_id,
                    special_request=special_request,
                )
                assert result.ai_job_id is not None
                background_tasks.add_task(
                    dispatch_ai_job,
                    result.ai_job_id,
                    draft.organization_id,
                )
                await _reply(
                    line,
                    event,
                    [
                        _text(
                            "收到了，謝謝告訴我們！我們馬上幫你看看有沒有更適合的毛孩，"
                            "找到後會再傳訊息通知你 🐾"
                        )
                    ],
                )
                return
            if settings.app_env.strip().lower() not in {"local", "test", "testing"}:
                await LineAdoptionConversationService(repository).finish_followup_without_ai(
                    adopter_user_id=draft.adopter_user_id
                )
                updated = await repository.get(draft.id)
                if updated is not None:
                    await _adoption_reply_for_state(
                        session,
                        line,
                        event,
                        draft=updated,
                        public_base_url=public_base_url,
                        lead=[_text("進階推薦目前未啟用，已保留你原本選定的毛孩。")],
                    )
                return
            target_animal_id = draft.ai_followup_target_animal_id
            draft.ai_followup_target_animal_id = None
            await session.flush()
            line_user_id = event.get("source", {}).get("userId")
            if line_user_id and draft.organization_id is not None:
                background_tasks.add_task(
                    _run_adoption_ai_followup_recommendations,
                    line,
                    line_user_id=line_user_id,
                    organization_id=draft.organization_id,
                    draft_id=draft.id,
                    exclude_animal_id=target_animal_id,
                    special_request=special_request,
                    public_base_url=public_base_url,
                )
            await _reply(
                line,
                event,
                [
                    _text(
                        "收到了，謝謝告訴我們！我們馬上幫你看看有沒有更適合的毛孩，"
                        "找到後會再傳訊息通知你 🐾"
                    )
                ],
            )
            return
        await _reply(
            line, event, [_text("AI 適配度分析還在進行中，完成後會馬上通知你，請稍等一下下 🤖")]
        )
        return
    if draft.current_step in CONTACT_EDIT_STATES:
        action, value = "save_contact", text.strip()
    elif draft.current_step == AdoptionDraftState.SELECTING_TARGET_ANIMAL.value:
        await _reply_adoption_animal_page(
            session, line, event, draft=draft, public_base_url=public_base_url, query=text
        )
        return
    elif draft.current_step in {
        AdoptionDraftState.AWAITING_ADOPTER_NAME.value,
        AdoptionDraftState.AWAITING_CONTACT_TIME.value,
    }:
        action, value = "answer", text.strip()
    elif draft.current_step == AdoptionDraftState.AWAITING_PHONE_NUMBER.value:
        action, value = "phone_number", text.strip()
    else:
        await _reply(line, event, [_text("目前步驟請使用選單按鈕操作，不需要輸入文字。")])
        return
    await LineAdoptionConversationService(
        repository, answer_validator=_adoption_answer_validator
    ).handle(
        token=None,
        adopter_user_id=draft.adopter_user_id,
        action=action,
        value=value,
        event_id=event.get("webhookEventId", ""),
    )
    updated = await repository.get_active_for_adopter(draft.adopter_user_id)
    if updated is not None:
        await _adoption_reply_for_state(
            session, line, event, draft=updated, public_base_url=public_base_url
        )


def _selection_service(session, organization_id: UUID) -> AnimalSelectionService:
    animals = AnimalRepository(session, organization_id)
    return AnimalSelectionService(
        animals,
        QrCodeRepository(session, organization_id),
        VolunteerReportingAuthorizationService(AuthenticationRepository(session), animals),
    )


async def _walk_confirmation_bubble(
    session,
    organization_id: UUID,
    candidate,
    *,
    public_base_url: str | None,
) -> dict:
    organization = await AuthenticationRepository(session).get_organization(organization_id)
    photo_url = None
    if candidate.animal.current_photo_key:
        try:
            photo_url = await ExternalAnimalPhotoService(session).issue_url(
                public_base_url=public_base_url,
                organization_id=organization_id,
                animal=candidate.animal,
                purpose=VOLUNTEER_WALK_PHOTO,
            )
        except Exception:
            logger.warning("animal confirmation photo unavailable", exc_info=True)
    return animal_confirmation_bubble(
        animal_name=candidate.animal.name,
        shelter_number=candidate.animal.shelter_number or "無收容編號",
        area_label=candidate.area.name if candidate.area else "未維護",
        organization_name=organization.name if organization else "目前收容所",
        photo_url=photo_url,
        confirm_data=urlencode({"action": "confirm_animal", "animal_id": str(candidate.animal.id)}),
    )


async def _search_result_bubble(
    session,
    *,
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
    query: str,
    page: int,
    public_base_url: str | None,
) -> dict:
    query = query.strip()
    if not query or len(query) > 80:
        raise DomainError("invalid_animal_search", "請輸入 1～80 個字的名字或收容編號", 422)
    result = await _selection_service(session, organization_id).search_page(
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        role="VOLUNTEER",
        query=query,
        page=page,
        page_size=5,
    )
    if not result.items:
        return prompt_bubble(
            title="沒有找到符合的毛孩",
            caption="散步回報",
            body_text="換個名字或收容編號再試一次。",
            glyph="📭",
            tone=PEACH,
            choices=[],
        )
    if result.total == 1:
        return await _walk_confirmation_bubble(
            session,
            organization_id,
            result.items[0],
            public_base_url=public_base_url,
        )
    choices = [
        (
            f"{item.animal.name}／{item.animal.shelter_number or '無編號'}",
            urlencode({"action": "select_animal", "animal_id": str(item.animal.id)}),
            "🐶",
        )
        for item in result.items
    ]
    if result.has_more:
        choices.append(
            (
                "顯示更多",
                urlencode({"action": "search_results", "query": query, "page": page + 1}),
                "＋",
            )
        )
    return prompt_bubble(
        title=f"找到 {result.total} 隻毛孩",
        caption=f"散步回報 · 第 {page} 頁",
        body_text="請核對名字與收容編號，再選擇要回報的毛孩。",
        glyph="🔎",
        tone=LILAC,
        choices=choices,
    )


async def _today_list_bubble(
    session,
    *,
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
    page: int,
) -> dict:
    authentication = AuthenticationRepository(session)
    organization = await authentication.get_organization(organization_id)
    if organization is None:
        raise DomainError("shelter_context_required", "目前收容所不存在", 409)
    animals = AnimalRepository(session, organization_id)
    result = await TodayAnimalListService(
        animals,
        CareReportRepository(session, organization_id),
        VolunteerReportingAuthorizationService(authentication, animals),
    ).list_today(
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        timezone_name=organization.timezone,
        page=page,
        page_size=5,
    )
    timezone = ZoneInfo(organization.timezone)
    rows: list[tuple[str, str, str, bool]] = []
    for item in result.unreported:
        animal = item.candidate.animal
        rows.append(
            (
                f"{animal.name}／{animal.shelter_number or '無編號'}",
                urlencode({"action": "select_animal", "animal_id": str(animal.id)}),
                "今天尚未回報",
                False,
            )
        )
    for item in result.reported:
        animal = item.candidate.animal
        latest = (
            item.latest_submitted_at.astimezone(timezone).strftime("%H:%M")
            if item.latest_submitted_at
            else "時間未知"
        )
        rows.append(
            (
                f"{animal.name}／{animal.shelter_number or '無編號'}",
                urlencode({"action": "select_animal", "animal_id": str(animal.id)}),
                f"已回報 {item.report_count} 次 · 最新 {latest}",
                True,
            )
        )
    total = result.unreported_total + result.reported_total
    if total == 0:
        return prompt_bubble(
            title="今天還沒有散步名單",
            caption="散步回報",
            body_text="目前沒有可回報的毛孩，若資料有誤請聯繫工作人員。",
            glyph="📭",
            tone=PEACH,
            choices=[("回到找動物", "action=find_dog", "←")],
        )
    shown = min(page * result.page_size, result.unreported_total) + min(
        page * result.page_size, result.reported_total
    )
    has_more = result.unreported_has_more or result.reported_has_more
    return daily_care_bubble(
        rows,
        done=result.reported_total,
        total=total,
        shown_through=shown,
        more_data=(urlencode({"action": "today_overview", "page": page + 1}) if has_more else None),
    )


def _find_dog_hub_bubble() -> dict:
    return prompt_bubble(
        title="要幫哪隻毛孩回報",
        caption="散步回報",
        body_text="選一種方式找到今天要回報的毛孩 🔎",
        glyph="🔎",
        tone=BUTTER,
        choices=[
            ("掃描 QR 貼紙", "action=qr_scan", "📷"),
            ("輸入編號或名字", "action=search_animal", "🔤"),
            ("看今日名單", "action=today_overview", "📋"),
        ],
    )


async def _walk_entry_bubble(
    session, *, user_id: UUID, organization_id: UUID, membership_id: UUID
) -> dict:
    animals = AnimalRepository(session, organization_id)
    await VolunteerReportingAuthorizationService(
        AuthenticationRepository(session), animals
    ).authorize(
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
    )
    draft = await CareReportDraftRepository(session, organization_id).get_active_for_volunteer(
        user_id
    )
    if draft is None:
        return _find_dog_hub_bubble()
    if (draft.modification_summary or {}).get("handoff_selection"):
        return await _handoff_switch_bubble(session, organization_id, draft)
    animal = await animals.get(draft.animal_id)
    animal_name = animal.name if animal is not None else "上一隻毛孩"
    return prompt_bubble(
        title="有一筆散步回報還沒完成",
        caption="散步回報",
        body_text=f"要繼續回報 {animal_name}，還是重新找動物？",
        glyph="📝",
        tone=BUTTER,
        choices=[
            (f"繼續回報 {animal_name}", "action=resume_draft", "↩"),
            ("重新找動物", "action=find_dog", "🔎"),
        ],
    )


async def _handoff_switch_bubble(session, organization_id: UUID, draft) -> dict:
    animals = AnimalRepository(session, organization_id)
    previous = await animals.get(draft.animal_id)
    candidate = (
        await animals.get(draft.candidate_animal_id)
        if draft.candidate_animal_id is not None
        else None
    )
    if candidate is None:
        raise DomainError("draft_switch_conflict", "回報草稿已變更，請重新確認", 409)
    previous_name = previous.name if previous is not None else "上一隻毛孩"
    return prompt_bubble(
        title="還有一筆回報沒送出",
        caption="散步回報",
        body_text=f"切換會清除 {previous_name} 的答案、照片與文字。",
        glyph="⚠️",
        tone=PEACH,
        choices=[
            (f"繼續回報 {previous_name}", "action=cancel_handoff_switch", "↩"),
            (f"改成回報 {candidate.name}", "action=confirm_handoff_switch", "🔄"),
        ],
    )


async def _handle_walk_report_command(session, line, event: dict, line_user_id: str) -> None:
    user_id, organization_id, membership_id, _ = await _resolve_context(session, line_user_id)
    handoff = None
    handoff_error: DomainError | None = None
    decision = None

    # A savepoint keeps handoff consumption and draft mutation atomic while
    # allowing the outer webhook transaction to record a safe failure result.
    async with session.begin_nested():
        animals = AnimalRepository(session, organization_id)
        try:
            handoff = await CareReportHandoffService(
                CareReportHandoffRepository(session, organization_id),
                authorization=VolunteerReportingAuthorizationService(
                    AuthenticationRepository(session), animals
                ),
            ).consume_pending_handoff(
                user_id=user_id,
                organization_id=organization_id,
            )
        except DomainError as error:
            if error.code not in {
                "no_pending_handoff",
                "handoff_already_consumed",
                "handoff_expired",
            }:
                raise
            handoff_error = error

        if handoff is not None:
            draft_repository = CareReportDraftRepository(session, organization_id)
            decision = await LineDraftService(
                draft_repository,
                ttl_seconds=get_settings().draft_ttl_seconds,
            ).select_handoff_animal(
                volunteer_user_id=user_id,
                membership_id=handoff.membership_id,
                animal_id=handoff.animal_id,
                source_event_id=event.get("webhookEventId", ""),
            )
            if decision.action.value == "created":
                await LineDraftConversationService(draft_repository).handle(
                    token=decision.token,
                    volunteer_user_id=user_id,
                    action="confirm_animal",
                    value=None,
                    event_id=event.get("webhookEventId", ""),
                )

    if handoff_error is not None:
        messages = []
        if handoff_error.code == "handoff_expired":
            messages.append(_text("動物確認已逾時，請重新掃描確認。"))
        messages.append(
            await _walk_entry_bubble(
                session,
                user_id=user_id,
                organization_id=organization_id,
                membership_id=membership_id,
            )
        )
        await _reply(line, event, messages)
        return

    assert handoff is not None and decision is not None
    if decision.action.value == "needs_switch_confirmation":
        await _reply(
            line,
            event,
            [await _handoff_switch_bubble(session, organization_id, decision.draft)],
        )
        return

    animal = await AnimalRepository(session, organization_id).get(handoff.animal_id)
    animal_name = animal.name if animal is not None else "這隻毛孩"
    await _reply_next_step(
        session,
        line,
        event,
        organization_id=organization_id,
        draft=decision.draft,
        raw_token=decision.token or "",
        lead=[
            _text(
                f"已恢復 {animal_name} 的未完成回報。"
                if decision.action.value == "resumed"
                else f"開始回報 {animal_name}。"
            )
        ],
    )


async def _answer_options(
    session,
    organization_id: UUID,
    state: DraftState,
    answers: dict,
    reconfirmation_keys: list[str] | None = None,
) -> list[EffectiveOption]:
    machine = DraftStateMachine(
        state=state,
        answers=DraftAnswers(dict(answers)),
        reconfirmation_keys=set(reconfirmation_keys or []),
    )
    key = machine.next_answer_key()
    options = await ObservationRepository(session, organization_id).effective_options(
        include_disabled_history=False
    )
    prefixes = {
        "walk_completion": "walk_completion.",
        "activity": "activity.",
        "gait": "gait.",
        "defecation": "defecation.",
        "animal_interaction": "animal_interaction.",
        "appearance_special_status": "appearance.",
    }
    prefix = prefixes[key]
    return [option for option in options if option.code.startswith(prefix)]


async def _answer_validator(session, organization_id: UUID):
    options = await ObservationRepository(session, organization_id).effective_options(
        include_disabled_history=False
    )
    return EffectiveObservationService(
        {
            option.code: EffectiveOption(
                code=option.code,
                display_name=option.display_name,
                description=option.description,
                requires_note=option.requires_note,
                active=option.status == "active",
            )
            for option in options
        }
    ).validate_answer


async def _note_validator(session, organization_id: UUID):
    options = await ObservationRepository(session, organization_id).effective_options(
        include_disabled_history=False
    )
    return EffectiveObservationService(
        {
            option.code: EffectiveOption(
                code=option.code,
                display_name=option.display_name,
                description=option.description,
                requires_note=option.requires_note,
                active=option.status == "active",
            )
            for option in options
        }
    ).validate_note_requirement


_CATEGORY_GLYPHS = {
    "walk_completion": "🚶",
    "activity": "⚡",
    "gait": "🐾",
    "defecation": "💩",
    "animal_interaction": "🐕",
    "appearance_special_status": "🔍",
}


async def _category_titles(session, organization_id: UUID) -> dict[str, str]:
    categories = await ObservationRepository(session, organization_id).categories()
    return {category.code: category.display_name for category in categories}


async def _options_requiring_note(session, organization_id: UUID, answers: dict) -> list[str]:
    repository = ObservationRepository(session, organization_id)
    options = await repository.effective_options(include_disabled_history=True)
    categories = await repository.categories(include_disabled=True)
    titles = {category.id: category.display_name for category in categories}
    by_code = {option.code: option for option in options}
    return [
        f"{titles.get(option.category_id, field)}：{option.display_name}"
        for field, code in answers.items()
        if (option := by_code.get(code)) is not None and option.requires_note
    ]


async def _reply_next_step(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    organization_id: UUID,
    draft,
    raw_token: str,
    lead: list[dict] | None = None,
    public_base_url: str | None = None,
) -> None:
    # A LINE reply token is single-use and short-lived, so a message that has to
    # precede the next step is passed in here and sent in the same reply call
    # rather than in a second reply that LINE would reject.
    lead_messages = lead or []
    state = DraftState(draft.current_step)
    if state == DraftState.SELECTING_ANIMAL:
        await _reply(line, event, [*lead_messages, _find_dog_hub_bubble()])
    elif state == DraftState.CONFIRMING_ANIMAL:
        if (draft.modification_summary or {}).get("handoff_selection"):
            card = await _handoff_switch_bubble(session, organization_id, draft)
        else:
            candidate = await _selection_service(session, organization_id).confirm(
                animal_id=draft.animal_id,
                user_id=draft.volunteer_user_id,
                organization_id=organization_id,
                membership_id=draft.membership_id,
                role="VOLUNTEER",
            )
            card = await _walk_confirmation_bubble(
                session, organization_id, candidate, public_base_url=public_base_url
            )
        await _reply(line, event, [*lead_messages, card])
    elif state in {
        DraftState.ANSWERING_WALK_COMPLETION,
        DraftState.ANSWERING_ACTIVITY,
        DraftState.ANSWERING_GAIT,
        DraftState.ANSWERING_DEFECATION,
        DraftState.ANSWERING_ANIMAL_INTERACTION,
        DraftState.ANSWERING_SPECIAL_STATUS,
    }:
        options = await _answer_options(
            session,
            organization_id,
            state,
            draft.answers,
            getattr(draft, "reconfirmation_keys", None),
        )
        machine = DraftStateMachine(
            state=state,
            answers=DraftAnswers(dict(draft.answers)),
            reconfirmation_keys=set(getattr(draft, "reconfirmation_keys", []) or []),
        )
        key = machine.next_answer_key()
        titles = await _category_titles(session, organization_id)
        await _reply(
            line,
            event,
            [
                *lead_messages,
                question_bubble(
                    options,
                    draft_token=raw_token,
                    step=state.value,
                    title=titles.get(key, key),
                    position=REQUIRED_ANSWER_KEYS.index(key) + 1,
                    total=len(REQUIRED_ANSWER_KEYS),
                    glyph=_CATEGORY_GLYPHS.get(key, "🐾"),
                ),
            ],
        )
    elif state == DraftState.AWAITING_STOOL_MEDIA:
        await _reply(
            line,
            event,
            [
                *lead_messages,
                prompt_bubble(
                    title="拍一張便便照片",
                    caption="散步回報 · 有拍最好",
                    body_text="直接在聊天室傳照片即可；這張只供照護判讀，不會出現在對外貼文。",
                    glyph="🔬",
                    tone=PEACH,
                    choices=[
                        ("這次略過", f"action=skip_stool_media&draft_token={raw_token}", "⏭"),
                        ("上一步", f"action=back&draft_token={raw_token}", "←"),
                    ],
                ),
            ],
        )
    elif state == DraftState.AWAITING_NOTE:
        required = await _options_requiring_note(session, organization_id, draft.answers)
        choices = (
            [("上一步", f"action=back&draft_token={raw_token}", "←")]
            if required
            else [
                ("略過補充", f"action=skip_note&draft_token={raw_token}", "⏭"),
                ("上一步", f"action=back&draft_token={raw_token}", "←"),
            ]
        )
        await _reply(
            line,
            event,
            [
                *lead_messages,
                prompt_bubble(
                    title="需要補充說明" if required else "今天有什麼想補充的嗎",
                    caption="散步回報 · 必填" if required else "散步回報 · 選填",
                    body_text=(
                        "請直接打字說明：\n" + "\n".join(f"・{item}" for item in required)
                        if required
                        else "健康或行為補充可直接打字傳送。"
                    ),
                    glyph="✍️" if required else "💭",
                    tone=PEACH if required else LILAC,
                    choices=choices,
                ),
            ],
        )
    elif state == DraftState.AWAITING_STORY:
        await _reply(
            line,
            event,
            [
                *lead_messages,
                prompt_bubble(
                    title="今天有發生什麼有趣的事嗎",
                    caption="散步回報 · 選填",
                    body_text="直接打字分享，這些會成為之後幫牠找家的小故事。",
                    glyph="✨",
                    tone=BUTTER,
                    choices=[
                        ("今天沒什麼特別的", f"action=skip_story&draft_token={raw_token}", "⏭"),
                        ("上一步", f"action=back&draft_token={raw_token}", "←"),
                    ],
                ),
            ],
        )
    elif state == DraftState.REVIEWING:
        review_options = await ObservationRepository(session, organization_id).effective_options(
            include_disabled_history=True
        )
        labels = {option.code: option.display_name for option in review_options}
        titles = await _category_titles(session, organization_id)
        rows = [
            (
                _CATEGORY_GLYPHS.get(key, "🐾"),
                titles.get(key, key),
                "今天沒觀察到這項" if value == UNOBSERVED else labels.get(value, value),
            )
            for key, value in draft.answers.items()
        ]
        animal = await AnimalRepository(session, organization_id).get(draft.animal_id)
        await _reply(
            line,
            event,
            [
                *lead_messages,
                summary_bubble(
                    rows,
                    note=draft.note,
                    story=draft.story,
                    animal_name=animal.name if animal is not None else "",
                    choices=[
                        (
                            "送出回報",
                            f"action={'submit' if raw_token else 'submit_current'}&draft_token={raw_token}",
                            "✅",
                        ),
                        ("再改一下", f"action=back&draft_token={raw_token}", "✏️"),
                        (
                            "取消回報",
                            f"action={'cancel' if raw_token else 'cancel_current'}&draft_token={raw_token}",
                            "🗑",
                        ),
                    ],
                ),
            ],
        )
    elif lead_messages:
        await _reply(line, event, lead_messages)


async def _handle_postback(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
    public_base_url: str | None,
) -> UUID | None:
    values = parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True)
    action = values.get("action", [""])[0]
    if action in {"walk_report", "start_care_report"}:
        await _reply(
            line,
            event,
            [
                await _walk_entry_bubble(
                    session,
                    user_id=user_id,
                    organization_id=organization_id,
                    membership_id=membership_id,
                )
            ],
        )
        return None
    if action == "find_dog":
        await _reply(line, event, [_find_dog_hub_bubble()])
        return None
    if action == "qr_scan":
        await _reply(
            line,
            event,
            [
                prompt_bubble(
                    title="掃描籠舍上的 QR 貼紙",
                    caption="散步回報",
                    body_text="點相機拍下 QR 貼紙；QR 只會幫你找到動物，仍需再確認。",
                    glyph="📷",
                    tone=SKY,
                    choices=[("改用輸入搜尋", "action=search_animal", "🔤")],
                )
            ],
        )
        return None
    if action == "search_animal":
        await _reply(
            line,
            event,
            [
                prompt_bubble(
                    title="輸入編號或名字",
                    caption="散步回報",
                    body_text="直接輸入名字或收容編號的一部分。",
                    glyph="🔤",
                    tone=LILAC,
                    choices=[],
                )
            ],
        )
        return None
    if action == "search_results":
        query = values.get("query", [""])[0].strip()
        try:
            page = int(values.get("page", ["1"])[0])
        except ValueError as exc:
            raise DomainError("invalid_pagination", "分頁參數無效", 422) from exc
        await _reply(
            line,
            event,
            [
                await _search_result_bubble(
                    session,
                    user_id=user_id,
                    organization_id=organization_id,
                    membership_id=membership_id,
                    query=query,
                    page=page,
                    public_base_url=public_base_url,
                )
            ],
        )
        return None
    if action in {"list_reportable_animals", "today_overview"}:
        try:
            page = int(values.get("page", ["1"])[0])
        except ValueError as exc:
            raise DomainError("invalid_pagination", "分頁參數無效", 422) from exc
        await _reply(
            line,
            event,
            [
                await _today_list_bubble(
                    session,
                    user_id=user_id,
                    organization_id=organization_id,
                    membership_id=membership_id,
                    page=page,
                )
            ],
        )
        return None
    token = values.get("draft_token", [""])[0]
    if action == "contact_staff":
        await _reply(line, event, [_text("請直接聯繫目前收容所的工作人員協助處理。")])
        return None
    if action == "reselect_animal":
        if not token:
            raise DomainError("draft_token_required", "缺少回報草稿識別", 422)
        draft = await CareReportDraftRepository(session, organization_id).get_by_token(token)
        if draft is None or draft.volunteer_user_id != user_id or draft.status != "active":
            raise DomainError("draft_access_denied", "草稿不存在或無法存取", 404)
        await _reply(
            line,
            event,
            [
                _text("請選擇要更換的動物；確認切換後，原有答案、照片與文字都不會沿用。"),
                _find_dog_hub_bubble(),
            ],
        )
        return None
    if action == "select_animal":
        animal_id = _uuid_value(values.get("animal_id", [""])[0])
        if animal_id is None:
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        candidate = await _selection_service(session, organization_id).confirm(
            animal_id=animal_id,
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            role="VOLUNTEER",
        )
        animal = candidate.animal
        bubble = await _walk_confirmation_bubble(
            session,
            organization_id,
            candidate,
            public_base_url=public_base_url,
        )
        if token:
            bubble["contents"]["body"]["contents"][-2]["action"]["data"] = urlencode(
                {
                    "action": "confirm_animal",
                    "animal_id": str(animal.id),
                    "draft_token": token,
                }
            )
            bubble["contents"]["body"]["contents"][-1]["action"]["data"] = urlencode(
                {"action": "reselect_animal", "draft_token": token}
            )
        await _reply(
            line,
            event,
            [bubble],
        )
        return None
    if action == "confirm_animal":
        animal_id = _uuid_value(values.get("animal_id", [""])[0])
        if animal_id is None:
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        candidate = await _selection_service(session, organization_id).confirm(
            animal_id=animal_id,
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            role="VOLUNTEER",
        )
        animal = candidate.animal
        draft_service = LineDraftService(
            CareReportDraftRepository(session, organization_id),
            ttl_seconds=get_settings().draft_ttl_seconds,
        )
        switch = values.get("switch", [""])[0] == "1"
        expected = _uuid_value(values.get("expected_animal_id", [""])[0])
        decision = await draft_service.select_confirmed_animal(
            volunteer_user_id=user_id,
            membership_id=membership_id,
            animal_id=animal.id,
            confirm_switch=switch,
            expected_current_animal_id=expected,
            source_event_id=event.get("webhookEventId", ""),
        )
        if decision.action.value == "needs_switch_confirmation":
            previous = await AnimalRepository(session, organization_id).get(
                decision.draft.animal_id
            )
            previous_name = previous.name if previous is not None else "上一隻毛孩"
            await _reply(
                line,
                event,
                [
                    prompt_bubble(
                        title="還有一筆回報沒送出",
                        caption="散步回報",
                        body_text=f"切換會清除 {previous_name} 的答案、照片與文字。",
                        glyph="⚠️",
                        tone=PEACH,
                        choices=[
                            (f"繼續回報 {previous_name}", "action=resume_draft", "↩"),
                            (
                                f"改成回報 {animal.name}",
                                urlencode(
                                    {
                                        "action": "confirm_animal",
                                        "animal_id": str(animal.id),
                                        "switch": "1",
                                        "expected_animal_id": str(decision.draft.animal_id),
                                    }
                                ),
                                "🔄",
                            ),
                        ],
                    )
                ],
            )
            return None
        draft = decision.draft
        raw_token = decision.token or token
        if (
            decision.action.value == "created"
            or DraftState(draft.current_step) == DraftState.CONFIRMING_ANIMAL
        ):
            await LineDraftConversationService(
                CareReportDraftRepository(session, organization_id)
            ).handle(
                token=raw_token or None,
                volunteer_user_id=user_id,
                action="confirm_animal",
                value=None,
                event_id=event.get("webhookEventId", ""),
            )
        message = (
            f"已改成回報 {animal.name}，舊內容已清除。"
            if decision.action.value == "switched"
            else f"開始回報 {animal.name}。"
        )
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=draft,
            raw_token=raw_token,
            lead=[_text(message)],
        )
        return None
    if action == "confirm_handoff_switch":
        draft_repository = CareReportDraftRepository(session, organization_id)
        draft = await draft_repository.get_active_for_volunteer(user_id)
        if draft is None or draft.candidate_animal_id is None:
            raise DomainError("handoff_switch_not_pending", "目前沒有待確認的動物切換", 409)
        authorized = await VolunteerReportingAuthorizationService(
            AuthenticationRepository(session), AnimalRepository(session, organization_id)
        ).authorize(
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            animal_id=draft.candidate_animal_id,
            animal_unavailable_status=409,
        )
        assert authorized.animal is not None
        switched = await LineDraftService(
            draft_repository,
            ttl_seconds=get_settings().draft_ttl_seconds,
        ).confirm_handoff_switch(volunteer_user_id=user_id)
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=switched,
            raw_token="",
            lead=[_text(f"已改成回報 {authorized.animal.name}，舊內容已清除。")],
        )
        return None
    if action == "cancel_handoff_switch":
        draft_repository = CareReportDraftRepository(session, organization_id)
        draft = await LineDraftService(
            draft_repository,
            ttl_seconds=get_settings().draft_ttl_seconds,
        ).cancel_handoff_switch(volunteer_user_id=user_id)
        await _selection_service(session, organization_id).confirm(
            animal_id=draft.animal_id,
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            role="VOLUNTEER",
        )
        draft = await LineDraftService(draft_repository).resume(draft.id, volunteer_user_id=user_id)
        animal = await AnimalRepository(session, organization_id).get(draft.animal_id)
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=draft,
            raw_token="",
            lead=[
                _text(f"已保留 {animal.name if animal is not None else '原本毛孩'} 的回報內容。")
            ],
            public_base_url=public_base_url,
        )
        return None
    if action == "resume_draft" and not token:
        draft = await CareReportDraftRepository(session, organization_id).get_active_for_volunteer(
            user_id
        )
        if draft is None:
            await _reply(line, event, [_text("目前沒有可繼續的回報。")])
            return None
        await _selection_service(session, organization_id).confirm(
            animal_id=draft.animal_id,
            user_id=user_id,
            organization_id=organization_id,
            membership_id=membership_id,
            role="VOLUNTEER",
        )
        draft = await LineDraftService(CareReportDraftRepository(session, organization_id)).resume(
            draft.id, volunteer_user_id=user_id
        )
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=draft,
            raw_token="",
            lead=[_text("已恢復未完成回報，請依下方卡片繼續。")],
            public_base_url=public_base_url,
        )
        return None
    if not token and action not in {
        "answer",
        "back",
        "skip_question",
        "skip_stool_media",
        "skip_note",
        "skip_story",
        "submit_current",
        "cancel_current",
    }:
        raise DomainError("draft_token_required", "缺少回報草稿識別", 422)
    draft_repository = CareReportDraftRepository(session, organization_id)
    draft = (
        await draft_repository.get_by_token(token)
        if token
        else await draft_repository.get_active_for_volunteer(user_id)
    )
    if draft is None:
        raise DomainError("draft_access_denied", "草稿不存在或無法存取", 404)
    if action == "cancel":
        draft.status = "cancelled"
        draft.current_step = DraftState.CANCELLED.value
        await session.flush()
        await _reply(line, event, [_text("已取消這次回報，沒有建立正式紀錄。")])
        return None
    validator = None
    note_validator = None
    if action in {"answer", "skip_note", "submit", "submit_current"}:
        validator = await _answer_validator(session, organization_id)
        note_validator = await _note_validator(session, organization_id)
    result = await LineDraftConversationService(
        draft_repository,
        answer_validator=validator,
        note_validator=note_validator,
    ).handle(
        token=token or None,
        volunteer_user_id=user_id,
        action=action,
        value=values.get("value", [None])[0],
        event_id=event.get("webhookEventId", ""),
    )
    if result.report_id is not None:
        animal = await AnimalRepository(session, organization_id).get(draft.animal_id)
        await _reply(line, event, [celebration_bubble(animal_name=animal.name if animal else "")])
    else:
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=draft,
            raw_token=token,
        )
    return result.report_id


def _uuid_value(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None


async def _select_line_flow(session, line_user_id: str, event: dict) -> str | None:
    """Route input by explicit entry, preserving inactive drafts and authorization."""
    values = parse_qs(event.get("postback", {}).get("data", ""))
    action = values.get("action", [""])[0]
    flow = values.get("flow", [""])[0]
    binding = await LineWebhookRepository(session).binding(line_user_id)
    entry = None
    if action == "back_to_default_menu":
        entry = "menu"
    elif action == "start_adoption_matching":
        await _get_or_create_adopter_identity(session, line_user_id)
        binding = await LineWebhookRepository(session).binding(line_user_id)
        entry = "adoption"
    elif _is_walk_report_command(event) or action in {"walk_report", "start_care_report"}:
        await _resolve_context(session, line_user_id)
        entry = "care_report"
    elif _is_growth_diary_command(event) or (
        flow == "growth_diary" and action in {"start_growth_diary", "view_growth_diary_history"}
    ):
        entry = "growth_diary"
    if action == "start_volunteer_application" or (
        event.get("message", {}).get("text", "").strip() == VOLUNTEER_APPLICATION_COMMAND
    ):
        entry = "menu"
    if binding is None:
        return None
    if entry is not None:
        binding.current_flow = entry
        await session.flush()
        return entry
    # Menu actions do not submit conversation answers.
    if (
        action in STAFF_MENU_ACTIONS
        or action in MENU_PLACEHOLDER_ACTIONS
        or action == "start_binding"
    ):
        return binding.current_flow
    current = binding.current_flow
    if current is None:
        active = []
        adoption = await _active_adoption_draft(session, line_user_id)
        if adoption is not None and adoption.expires_at > datetime.now(timezone.utc):
            active.append("adoption")
        if await _resolve_growth_diary_pending(session, line_user_id) is not None:
            active.append("growth_diary")
        try:
            user_id, organization_id, _, _ = await _resolve_context(session, line_user_id)
        except DomainError:
            pass
        else:
            draft = await CareReportDraftRepository(
                session, organization_id
            ).get_active_for_volunteer(user_id)
            if draft is not None and draft.expires_at > datetime.now(timezone.utc):
                active.append("care_report")
        if len(active) > 1:
            raise DomainError(
                "line_flow_required",
                "你有多份未完成的紀錄，請先點選散步回報、領養媒合，或輸入「毛孩日記」再繼續。",
                409,
            )
        current = active[0] if active else None
        if current is not None:
            binding.current_flow = current
            await session.flush()
    if current == "menu":
        raise DomainError(
            "line_flow_required",
            "請先由選單選擇散步回報或領養媒合；記錄日記請輸入「毛孩日記」。原本的草稿仍保留。",
            409,
        )
    if event.get("type") == "postback" and action:
        expected = flow if flow in {"adoption", "growth_diary"} else "care_report"
        if current is not None and expected != current:
            raise DomainError(
                "line_flow_mismatch",
                "這是另一個流程的舊卡片，請先切回對應入口再繼續。草稿仍保留。",
                409,
            )
    return current


@router.post("/webhook", openapi_extra={"security": []})
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()
    settings = get_settings()
    verify_line_signature(
        raw_body=raw_body,
        signature=x_line_signature,
        channel_secret=settings.line_channel_secret,
    )
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise DomainError("invalid_webhook_payload", "LINE Webhook 格式無效", 400) from exc

    line = LineMessagingApiAdapter()
    public_base_url = _line_public_base_url(request)
    results = []
    async with session_factory() as session:
        for event in payload.get("events", []):
            event_id = event.get("webhookEventId")
            if not event_id:
                results.append(
                    {"webhook_event_id": "", "status": "rejected", "reason": "missing_event_id"}
                )
                continue
            report_id_to_dispatch = None
            async with _growth_diary_event_transaction(
                session,
                event_id=event_id,
                background_tasks=background_tasks,
            ) as growth_diary_event_boundary:
                identity = LineWebhookRepository(session)
                stored_event, claimed = await identity.claim_event(
                    webhook_event_id=event_id,
                    event_type=event.get("type", "unknown"),
                    redelivery=bool(event.get("deliveryContext", {}).get("isRedelivery")),
                )
                if not claimed:
                    results.append({"webhook_event_id": event_id, "status": "duplicate_ignored"})
                    continue
                try:
                    source = event.get("source", {})
                    line_user_id = source.get("userId")
                    if not line_user_id:
                        raise DomainError("line_user_missing", "LINE 使用者識別不存在", 403)
                    line.ensure_recipient_allowed(line_user_id)
                    current_flow = await _select_line_flow(session, line_user_id, event)
                    if await _handle_menu_action(line, event):
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    if _is_walk_report_command(event):
                        await _handle_walk_report_command(
                            session,
                            line,
                            event,
                            line_user_id,
                        )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    postback_values = (
                        parse_qs(
                            event.get("postback", {}).get("data", ""),
                            keep_blank_values=True,
                        )
                        if event.get("type") == "postback"
                        else {}
                    )
                    action = postback_values.get("action", [""])[0]
                    growth_diary_entry_action = (
                        action if postback_values.get("flow", [""])[0] == "growth_diary" else None
                    )
                    if action == "start_adoption_matching":
                        await _handle_adoption_start(
                            session,
                            line,
                            event,
                            line_user_id,
                            public_base_url=public_base_url,
                        )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    if await _handle_public_volunteer_application_entry(session, line, event):
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    adoption_draft = (
                        await _active_adoption_draft(session, line_user_id)
                        if current_flow in {None, "adoption"}
                        else None
                    )
                    if (
                        adoption_draft is not None
                        and event.get("type") == "postback"
                        and postback_values.get("flow", [""])[0] == "adoption"
                    ):
                        await _handle_adoption_postback(
                            session,
                            line,
                            event,
                            draft=adoption_draft,
                            public_base_url=public_base_url,
                            background_tasks=background_tasks,
                        )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    if (
                        adoption_draft is not None
                        and event.get("type") == "message"
                        and event.get("message", {}).get("type") == "text"
                    ):
                        await _handle_adoption_text(
                            session,
                            line,
                            event,
                            draft=adoption_draft,
                            text=event["message"].get("text", ""),
                            public_base_url=public_base_url,
                            background_tasks=background_tasks,
                        )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    if (
                        adoption_draft is not None
                        and event.get("type") == "message"
                        and event.get("message", {}).get("type") == "image"
                    ):
                        await _reply(
                            line,
                            event,
                            [
                                build_info_card(
                                    "領養媒合目前不接受照片，請使用卡片按鈕繼續。", accent_index=0
                                )
                            ],
                        )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    growth_diary_pending = (
                        await _resolve_growth_diary_pending(session, line_user_id)
                        if current_flow in {None, "growth_diary"}
                        and not _is_growth_diary_command(event)
                        and action != "start_growth_diary"
                        else None
                    )
                    if growth_diary_pending is not None:
                        diary_adopter_user_id, pending_draft = growth_diary_pending
                        if event.get("type") == "postback":
                            await _handle_growth_diary_postback(
                                session,
                                line,
                                event,
                                adopter_user_id=diary_adopter_user_id,
                                pending_draft=pending_draft,
                                public_base_url=public_base_url,
                            )
                        elif event.get("type") == "message" and event.get("message", {}).get(
                            "type"
                        ) in {"image", "text"}:
                            await _handle_growth_diary_message(
                                session,
                                line,
                                event,
                                adopter_user_id=diary_adopter_user_id,
                                pending_draft=pending_draft,
                                event_boundary=growth_diary_event_boundary,
                            )
                        else:
                            await _reply(
                                line,
                                event,
                                [_text("請直接傳照片或文字記錄成長日記，暫不支援這種訊息類型。")],
                            )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    if growth_diary_entry_action in {
                        "start_growth_diary",
                        "start_growth_diary_entry",
                        "select_growth_diary_animal",
                        "view_growth_diary_history",
                        "snooze_growth_diary_reminder",
                    }:
                        # Never lazily create an identity here (unlike adoption
                        # entry) — if this LINE user has no binding at all, they
                        # cannot possibly have a completed AdoptionInquiry yet.
                        binding = await LineWebhookRepository(session).binding(line_user_id)
                        if binding is None:
                            await _reply(
                                line,
                                event,
                                [_text("請先透過「領養媒合」完成一次領養意願，才能使用毛孩日記。")],
                            )
                        else:
                            await set_authentication_user_scope(session, binding.user_id)
                            await _handle_growth_diary_postback(
                                session,
                                line,
                                event,
                                adopter_user_id=binding.user_id,
                                pending_draft=None,
                                public_base_url=public_base_url,
                            )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    if _is_growth_diary_command(event):
                        binding = await LineWebhookRepository(session).binding(line_user_id)
                        if binding is None:
                            await _reply(
                                line,
                                event,
                                [_text("請先透過「領養媒合」完成一次領養意願，才能使用毛孩日記。")],
                            )
                        else:
                            await set_authentication_user_scope(session, binding.user_id)
                            await _reply_growth_diary_entry_choice(
                                session, line, event, adopter_user_id=binding.user_id
                            )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    if current_flow in {"adoption", "growth_diary"}:
                        raise DomainError(
                            "line_flow_resume_required",
                            "這個流程目前沒有可填寫的步驟，請重新點選領養媒合或輸入「毛孩日記」。",
                            409,
                        )
                    (
                        user_id,
                        organization_id,
                        membership_id,
                        membership_role,
                    ) = await _resolve_context(session, line_user_id)
                    if event.get("type") == "postback":
                        if await _handle_staff_menu_action(
                            session,
                            line,
                            event,
                            organization_id=organization_id,
                            role=membership_role,
                        ):
                            await identity.complete_event(stored_event)
                            results.append({"webhook_event_id": event_id, "status": "processed"})
                            continue
                        report_id_to_dispatch = await _handle_postback(
                            session,
                            line,
                            event,
                            user_id=user_id,
                            organization_id=organization_id,
                            membership_id=membership_id,
                            public_base_url=public_base_url,
                        )
                    elif (
                        event.get("type") == "message"
                        and event.get("message", {}).get("type") == "text"
                    ):
                        draft_repository = CareReportDraftRepository(session, organization_id)
                        draft = await draft_repository.get_active_for_volunteer(user_id)
                        text_value = event["message"].get("text", "").strip()
                        if draft is not None and draft.current_step in {
                            DraftState.AWAITING_NOTE.value,
                            DraftState.AWAITING_STORY.value,
                        }:
                            action = (
                                "note"
                                if draft.current_step == DraftState.AWAITING_NOTE.value
                                else "story"
                            )
                            validator = await _note_validator(session, organization_id)
                            await LineDraftConversationService(
                                draft_repository, note_validator=validator
                            ).handle(
                                token=None,
                                volunteer_user_id=user_id,
                                action=action,
                                value=text_value,
                                event_id=event_id,
                            )
                            await _reply_next_step(
                                session,
                                line,
                                event,
                                organization_id=organization_id,
                                draft=draft,
                                raw_token="",
                            )
                        elif text_value:
                            await _reply(
                                line,
                                event,
                                [
                                    await _search_result_bubble(
                                        session,
                                        user_id=user_id,
                                        organization_id=organization_id,
                                        membership_id=membership_id,
                                        query=text_value,
                                        page=1,
                                        public_base_url=public_base_url,
                                    )
                                ],
                            )
                    elif (
                        event.get("type") == "message"
                        and event.get("message", {}).get("type") == "image"
                    ):
                        draft = await CareReportDraftRepository(
                            session, organization_id
                        ).get_active_for_volunteer(user_id)
                        if draft is None:
                            image = await line.get_image_content(message_id=event["message"]["id"])
                            raw_token = decode_qr_image(image.content)
                            candidate = await _selection_service(
                                session, organization_id
                            ).resolve_qr(
                                raw_token=raw_token,
                                user_id=user_id,
                                organization_id=organization_id,
                                membership_id=membership_id,
                                role="VOLUNTEER",
                            )
                            await _reply(
                                line,
                                event,
                                [
                                    await _walk_confirmation_bubble(
                                        session,
                                        organization_id,
                                        candidate,
                                        public_base_url=public_base_url,
                                    )
                                ],
                            )
                            await identity.complete_event(stored_event)
                            results.append({"webhook_event_id": event_id, "status": "processed"})
                            continue
                        if draft.current_step != DraftState.AWAITING_STOOL_MEDIA.value:
                            raise DomainError("invalid_draft_step", "目前回報步驟不接受照片", 409)
                        try:
                            await LineImageService(line, MinioStorageAdapter()).attach_to_draft(
                                message_id=event["message"]["id"],
                                organization_id=organization_id,
                                object_key=f"drafts/{draft.id}/{event_id}.media",
                                draft_id=draft.id,
                                source_event_id=event_id,
                                subject="stool",
                                session=session,
                            )
                        except Exception as error:
                            error_code = (
                                error.code
                                if isinstance(error, DomainError)
                                else "media_processing_failed"
                            )
                            await identity.complete_event(
                                stored_event, status="processed", error_code=error_code
                            )
                            await _reply(
                                line, event, [_text("照片處理失敗，請重新傳送或略過照片。")]
                            )
                            results.append(
                                {
                                    "webhook_event_id": event_id,
                                    "status": "processed",
                                    "reason": error_code,
                                }
                            )
                            continue
                        await LineDraftConversationService(
                            CareReportDraftRepository(session, organization_id)
                        ).handle(
                            token=None,
                            volunteer_user_id=user_id,
                            action="stool_media_attached",
                            value=None,
                            event_id=event_id,
                        )
                        await _reply_next_step(
                            session,
                            line,
                            event,
                            organization_id=organization_id,
                            draft=draft,
                            raw_token="",
                            lead=[_text("便便照片已附加。")],
                        )
                    await identity.complete_event(stored_event)
                    results.append({"webhook_event_id": event_id, "status": "processed"})
                except DomainError as error:
                    await identity.complete_event(
                        stored_event, status="failed", error_code=error.code
                    )
                    reply_message: dict
                    if error.code in {"line_binding_required", "shelter_context_required"}:
                        if (
                            error.code == "shelter_context_required"
                            and await _is_adopter_only_line_user(session, line_user_id)
                        ):
                            reply_message = _adopter_lost_message()
                        else:
                            reply_message = _text(_liff_binding_message())
                    else:
                        reply_message = _text(error.message)
                    # When the failure came from the LINE API itself the reply
                    # token is already spent or invalid; replying again would
                    # raise a second time, escape this handler and roll back the
                    # event claim, making LINE redeliver the event.
                    if error.code not in {
                        "line_api_unavailable",
                        "line_recipient_not_allowlisted",
                    }:
                        try:
                            await _reply(line, event, [reply_message])
                        except DomainError:
                            pass
                    results.append(
                        {"webhook_event_id": event_id, "status": "rejected", "reason": error.code}
                    )
            if report_id_to_dispatch is not None:
                await ReportJobDispatchService(session_factory).dispatch(
                    organization_id=organization_id,
                    report_id=report_id_to_dispatch,
                )
    return {"accepted": True, "event_results": results}
