from __future__ import annotations

# LINE message payloads intentionally mirror the Messaging API's nested JSON
# shape; E501 is suppressed for those literal payloads only.
# ruff: noqa: E501
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import APIRouter, Header, Request
from services.api.app.api.errors import DomainError
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.application.line_adoption_conversation import (
    LineAdoptionConversationService,
)
from services.api.app.application.line_adoption_draft_service import LineAdoptionDraftService
from services.api.app.application.line_adoption_flex import (
    MatchReportCard,
    ShelterCard,
    build_match_report,
    build_shelter_carousel,
)
from services.api.app.application.line_draft_conversation import (
    LineDraftConversationService,
)
from services.api.app.application.line_draft_service import LineDraftService
from services.api.app.application.line_growth_diary_flex import (
    AdoptedAnimalOption,
    build_animal_picker,
)
from services.api.app.application.line_image_service import LineImageService
from services.api.app.application.line_message_presenter import quick_reply_for_options
from services.api.app.application.line_webhook_session import LineWebhookSessionService
from services.api.app.application.media_access import MediaAccessService
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.application.ports.line_messaging import LineMessagingPort
from services.api.app.application.report_job_dispatch import ReportJobDispatchService
from services.api.app.config.settings import get_settings
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.domain.line_care_report_state import (
    DraftAnswers,
    DraftState,
    DraftStateMachine,
)
from services.api.app.domain.line_webhook_security import verify_line_signature
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.observability.logging import get_logger
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.growth_diary import GrowthDiaryDraft
from services.api.app.persistence.models.identity import LineUserBinding, User
from services.api.app.persistence.models.shelter_area import ShelterArea
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
)
from services.api.app.persistence.repositories.adoption_inquiry_repository import (
    list_inquiries_for_adopter,
)
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.growth_diary_repository import (
    GrowthDiaryRepository,
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
from services.api.app.persistence.repositories.organization_repository import (
    OrganizationRepository,
)
from services.api.app.persistence.repositories.reportable_scope_repository import (
    ReportableScopeRepository,
)
from sqlalchemy import select

router = APIRouter(prefix="/v1/line", tags=["LINE Bot"])

VOLUNTEER_APPLICATION_COMMAND = "我要報名志工"


async def _resolve_context(session, line_user_id: str) -> tuple[UUID, UUID, UUID]:
    identity = LineWebhookRepository(session)
    authentication = AuthenticationRepository(session)
    webhook_session = await LineWebhookSessionService(identity, authentication).resolve(
        line_user_id
    )
    membership = (await authentication.memberships(webhook_session.user_id, active_only=True))[0]
    return webhook_session.user_id, webhook_session.organization_id, membership.id


async def _reply(line: LineMessagingPort, event: dict, messages: list[dict]) -> None:
    reply_token = event.get("replyToken")
    if reply_token:
        await line.reply(reply_token=reply_token, messages=messages)


def _text(message: str) -> dict:
    return {"type": "text", "text": message}


def _liff_binding_message() -> str:
    return f"請先開啟 LIFF 完成身分綁定或選擇收容所：https://liff.line.me/{get_settings().liff_id}"


def _action(label: str, data: str, *, display_text: str | None = None) -> dict:
    """A raw postback action — use inside template `actions` arrays
    (Buttons/Confirm/Carousel templates), where LINE expects the action
    object directly, unlike quickReply.items (see `_postback` below)."""
    return {
        "type": "postback",
        "label": label[:20],
        "data": data,
        "displayText": display_text or label,
    }


def _volunteer_application_liff_url() -> str:
    return f"https://liff.line.me/{get_settings().liff_id}"


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
    await _reply(line, event, [_volunteer_application_entry_message()])
    return True


def _postback(label: str, data: str, *, display_text: str | None = None) -> dict:
    """A quickReply item — LINE wraps the action object in `{type, action}`
    here, unlike template `actions` arrays (see `_action` above). Mixing the
    two shapes up is an easy, LINE-API-shaped mistake: the mock adapter used
    in tests never validates the real schema, so only a real LINE channel
    ever catches it."""
    return {"type": "action", "action": _action(label, data, display_text=display_text)}


async def _animal_photo_url(organization_id: UUID, animal) -> str | None:
    """Best-effort signed photo URL for a Flex report card's hero image —
    same MinIO signing as `_animal_confirmation_messages`, but tolerant of a
    missing/unreadable photo since the card still reads fine without one."""
    if not animal.current_photo_key:
        return None
    try:
        return await MediaAccessService(MinioStorageAdapter(), organization_id).signed_url(
            media_organization_id=organization_id,
            object_key=animal.current_photo_key,
            expires_seconds=300,
        )
    except Exception:
        return None


async def _animal_confirmation_messages(session, animal, organization_id: UUID) -> list[dict]:
    messages = []
    if animal.current_photo_key:
        try:
            photo_url = await MediaAccessService(MinioStorageAdapter(), organization_id).signed_url(
                media_organization_id=organization_id,
                object_key=animal.current_photo_key,
                expires_seconds=300,
            )
            messages.append(
                {
                    "type": "image",
                    "originalContentUrl": photo_url,
                    "previewImageUrl": photo_url,
                }
            )
        except Exception:
            # The identity confirmation remains available when the current
            # photo cannot be fetched; the failure is not a reason to change
            # the selected animal.
            pass
    area_label = "未維護"
    if animal.area_id is not None:
        result = await session.execute(
            select(ShelterArea.name).where(
                ShelterArea.id == animal.area_id,
                ShelterArea.organization_id == organization_id,
            )
        )
        area_label = result.scalar_one_or_none() or area_label
    messages.append(_text(f"所在籠位／區域：{area_label}"))
    return messages


async def _reportable_animals(
    session,
    organization_id: UUID,
    volunteer_user_id: UUID,
    *,
    draft_token: str | None = None,
) -> list[dict]:
    animals = await AnimalRepository(session, organization_id).search("")
    allowed = await ReportableScopeRepository(session, organization_id).active_animal_ids(
        volunteer_user_id=volunteer_user_id
    )
    action = "select_animal"
    return [
        _postback(
            f"{animal.name}／{animal.shelter_number or '無收容編號'}",
            urlencode(
                {
                    "action": action,
                    "animal_id": str(animal.id),
                    **({"draft_token": draft_token} if draft_token else {}),
                }
            ),
        )
        for animal in animals
        if animal.id in allowed
    ][:6]


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
        "care_completion": "care_completion.",
        "walk_completion": "walk_completion.",
        "feeding": "feeding.",
        "water": "water.",
        "activity": "activity.",
        "urination": "urination.",
        "defecation": "defecation.",
        "resource_guarding": "resource_guarding.",
        "human_interaction": "human_interaction.",
        "animal_interaction": "animal_interaction.",
        "emotion": "emotion.",
        "walk_reaction": "walk.",
        "appearance_special_status": "appearance_special_status.",
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


async def _reply_next_step(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    organization_id: UUID,
    draft,
    raw_token: str,
) -> None:
    state = DraftState(draft.current_step)
    if state in {
        DraftState.ANSWERING_COMPLETION,
        DraftState.ANSWERING_FEEDING,
        DraftState.ANSWERING_WATER,
        DraftState.ANSWERING_ACTIVITY,
        DraftState.ANSWERING_ELIMINATION,
        DraftState.ANSWERING_BEHAVIOR,
        DraftState.ANSWERING_SPECIAL_STATUS,
    }:
        options = await _answer_options(
            session,
            organization_id,
            state,
            draft.answers,
            getattr(draft, "reconfirmation_keys", None),
        )
        answer_message = quick_reply_for_options(options, draft_token=raw_token, step=state.value)
        answer_message["quickReply"]["items"].append(
            _postback("上一步", f"action=back&draft_token={raw_token}")
        )
        await _reply(
            line,
            event,
            [answer_message],
        )
    elif state == DraftState.AWAITING_MEDIA:
        await _reply(
            line,
            event,
            [
                _text("可以傳送一張或多張照片；若要略過，請按下略過照片。"),
                {
                    "type": "template",
                    "altText": "照片選擇",
                    "template": {
                        "type": "buttons",
                        "text": "照片",
                        "actions": [
                            _action("略過照片", f"action=skip_media&draft_token={raw_token}"),
                            _action("上一步", f"action=back&draft_token={raw_token}"),
                        ],
                    },
                },
            ],
        )
    elif state == DraftState.AWAITING_NOTE:
        await _reply(
            line,
            event,
            [
                _text("心得可直接輸入；若沒有補充，請按下略過心得。"),
                {
                    "type": "template",
                    "altText": "心得選擇",
                    "template": {
                        "type": "buttons",
                        "text": "心得",
                        "actions": [
                            _action("略過心得", f"action=skip_note&draft_token={raw_token}"),
                            _action("上一步", f"action=back&draft_token={raw_token}"),
                        ],
                    },
                },
            ],
        )
    elif state == DraftState.REVIEWING:
        review_options = await ObservationRepository(session, organization_id).effective_options(
            include_disabled_history=True
        )
        labels = {option.code: option.display_name for option in review_options}
        summary_lines = [
            f"{key}：{labels.get(value, value)}" for key, value in draft.answers.items()
        ]
        if draft.note:
            summary_lines.append(f"心得：{draft.note}")
        await _reply(
            line,
            event,
            [
                _text("回報摘要：\n" + "\n".join(summary_lines) + "\n\n確認送出前仍可修改。"),
                {
                    "type": "template",
                    "altText": "回報確認",
                    "template": {
                        "type": "buttons",
                        "text": "回報摘要",
                        "actions": [
                            _action(
                                "送出回報",
                                f"action={'submit' if raw_token else 'submit_current'}&draft_token={raw_token}",
                            ),
                            _action(
                                "取消回報",
                                f"action={'cancel' if raw_token else 'cancel_current'}&draft_token={raw_token}",
                            ),
                            _action(
                                "修改",
                                f"action=back&draft_token={raw_token}",
                            ),
                            _action(
                                "更換動物",
                                f"action=reselect_animal&draft_token={raw_token}",
                            ),
                        ],
                    },
                },
            ],
        )


# 領養媒合問卷是固定的少量選項（非 DB 管理的觀察詞彙），代碼與 domain 層
# （adoption_matching.py／line_adoption_state.py）及既有測試使用的值保持一致。
_ADOPTION_QUESTION_OPTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "housing_type": (
        ("house", "透天／獨棟房屋"),
        ("apartment_small", "小坪數公寓"),
        ("apartment_large", "大坪數公寓"),
    ),
    "dog_experience": (
        ("first_time", "第一次養狗"),
        ("experienced", "有養狗經驗"),
    ),
    "other_pets": (
        ("none", "沒有其他寵物"),
        ("has_cats", "家中有貓"),
        ("has_dogs", "家中有其他狗"),
    ),
    "household_members": (
        ("adults_only", "只有成年人"),
        ("has_children", "家中有小孩"),
    ),
    "work_schedule": (
        ("work_from_home", "在家工作"),
        ("flexible", "工作時間彈性"),
        ("full_time_work", "全職外出工作"),
        ("little_time_at_home", "在家時間較少"),
        ("retired", "退休／全天在家"),
    ),
    "preferred_size": (
        ("small", "小型犬"),
        ("medium", "中型犬"),
        ("large", "大型犬"),
    ),
    "preferred_energy": (
        ("low", "文靜"),
        ("medium", "活動力適中"),
        ("high", "活潑好動"),
    ),
}

_ADOPTION_QUESTION_LABEL: dict[str, str] = {
    "housing_type": "居住環境",
    "dog_experience": "養狗經驗",
    "other_pets": "家中其他寵物",
    "household_members": "家庭成員",
    "work_schedule": "作息時間",
    "preferred_size": "希望的體型",
    "preferred_energy": "希望的活動力",
}

_ADOPTION_STATE_QUESTION_KEY: dict[AdoptionDraftState, str] = {
    AdoptionDraftState.ANSWERING_PREFERENCE_HOUSING: "housing_type",
    AdoptionDraftState.ANSWERING_PREFERENCE_EXPERIENCE: "dog_experience",
    AdoptionDraftState.ANSWERING_PREFERENCE_OTHER_PETS: "other_pets",
    AdoptionDraftState.ANSWERING_PREFERENCE_HOUSEHOLD: "household_members",
    AdoptionDraftState.ANSWERING_PREFERENCE_SCHEDULE: "work_schedule",
    AdoptionDraftState.ANSWERING_PREFERENCE_SIZE: "preferred_size",
    AdoptionDraftState.ANSWERING_PREFERENCE_ENERGY: "preferred_energy",
    AdoptionDraftState.ANSWERING_HOUSING: "housing_type",
    AdoptionDraftState.ANSWERING_EXPERIENCE: "dog_experience",
    AdoptionDraftState.ANSWERING_OTHER_PETS: "other_pets",
    AdoptionDraftState.ANSWERING_HOUSEHOLD: "household_members",
    AdoptionDraftState.ANSWERING_SCHEDULE: "work_schedule",
}


def _adoption_answer_validator(key: str, value: str) -> None:
    options = _ADOPTION_QUESTION_OPTIONS.get(key)
    if options is not None and value not in {code for code, _ in options}:
        raise DomainError("invalid_answer_value", f"不支援的領養問卷答案：{key}", 422)


async def _get_or_create_adopter_identity(session, line_user_id: str) -> UUID:
    """Lazily create a User+LineUserBinding for a prospective adopter on first
    touch — mirrors VolunteerAccessService.submit()'s identity bootstrap, but
    this LINE user never gains an OrganizationMembership."""
    identity = LineWebhookRepository(session)
    binding = await identity.binding(line_user_id)
    if binding is not None:
        return binding.user_id
    user = await identity.add(User(display_name="LINE 領養人", status="active"))
    binding = await identity.add(
        LineUserBinding(line_user_id=line_user_id, user_id=user.id, status="active")
    )
    return binding.user_id


async def _resolve_adoption_draft_context(
    session, line_user_id: str
) -> tuple[UUID, UUID | None] | None:
    """Return (adopter_user_id, organization_id) for a LINE user with an
    active AdoptionDraft, without ever resolving Membership. organization_id
    is None while the adopter is still choosing a shelter. Returns None when
    this LINE user has no binding or no active adoption draft at all —
    callers should then fall back to the normal Membership-based resolution
    (`_resolve_context`), which is left completely untouched."""
    binding = await LineWebhookRepository(session).binding(line_user_id)
    if binding is None:
        return None
    draft = await AdoptionDraftRepository(session, None).get_active_for_adopter(binding.user_id)
    if draft is None:
        return None
    return binding.user_id, draft.organization_id


def _adoption_cancel_item() -> dict:
    return _postback("取消", urlencode({"action": "cancel", "flow": "adoption"}))


def _adoption_cancel_action() -> dict:
    """Template-actions[] variant of `_adoption_cancel_item` — see `_action` vs `_postback`."""
    return _action("取消", urlencode({"action": "cancel", "flow": "adoption"}))


# Rich Menu switching is purely additive: every setting below defaults to
# None, so an environment that hasn't published/configured these menus yet
# (e.g. most tests) sees no `link_rich_menu` calls at all — see
# scripts/sync_line_rich_menu.py for how these IDs get produced.
_ADOPTION_STATE_RICH_MENU_SETTING: dict[AdoptionDraftState, str] = {
    AdoptionDraftState.SELECTING_ORGANIZATION: "line_rich_menu_region_select_id",
    AdoptionDraftState.CHOOSING_PATH: "line_rich_menu_path_select_id",
}

_logger = get_logger(__name__)


def _line_user_id_from_event(event: dict) -> str | None:
    return event.get("source", {}).get("userId")


async def _link_rich_menu_best_effort(
    line: LineMessagingPort, *, rich_menu_id: str, line_user_id: str
) -> None:
    """Switching a user's personal Rich Menu is cosmetic — a transient LINE
    API failure here must never fail (or roll back) the underlying
    conversation action that already succeeded."""
    try:
        await line.link_rich_menu(rich_menu_id=rich_menu_id, user_id=line_user_id)
    except Exception:
        _logger.warning(
            "rich_menu_switch_failed", extra={"rich_menu_id": rich_menu_id}, exc_info=True
        )


async def _sync_adoption_rich_menu(
    line: LineMessagingPort, event: dict, state: AdoptionDraftState
) -> None:
    setting_name = _ADOPTION_STATE_RICH_MENU_SETTING.get(state)
    if setting_name is None:
        return
    rich_menu_id = getattr(get_settings(), setting_name)
    line_user_id = _line_user_id_from_event(event)
    if not rich_menu_id or not line_user_id:
        return
    await _link_rich_menu_best_effort(line, rich_menu_id=rich_menu_id, line_user_id=line_user_id)


async def _revert_adoption_rich_menu(line: LineMessagingPort, event: dict) -> None:
    default_id = get_settings().line_rich_menu_default_id
    line_user_id = _line_user_id_from_event(event)
    if not default_id or not line_user_id:
        return
    await _link_rich_menu_best_effort(line, rich_menu_id=default_id, line_user_id=line_user_id)


async def _sync_volunteer_rich_menu(line: LineMessagingPort, event: dict) -> None:
    """Switches a bound volunteer's personal Rich Menu to the volunteer menu
    on every successful interaction — the account-wide default is adoption-
    only, so this is what gets a volunteer back to their own menu (both right
    after LIFF binding, and self-healing on every later interaction)."""
    rich_menu_id = get_settings().line_rich_menu_volunteer_id
    line_user_id = _line_user_id_from_event(event)
    if not rich_menu_id or not line_user_id:
        return
    await _link_rich_menu_best_effort(line, rich_menu_id=rich_menu_id, line_user_id=line_user_id)


async def _adoption_reply_for_state(
    session, line: LineMessagingPort, event: dict, *, draft
) -> None:
    state = AdoptionDraftState(draft.current_step)
    await _sync_adoption_rich_menu(line, event, state)
    if state == AdoptionDraftState.SELECTING_ORGANIZATION:
        # The region choices themselves live on the Rich Menu (switched above,
        # see infra/local/line-rich-menu.yaml's region_select entries); this
        # is just the in-chat nudge plus a way to abandon the flow.
        await _reply(
            line,
            event,
            [
                {
                    "type": "text",
                    "text": "請從下方選單選擇想去的地區。",
                    "quickReply": {"items": [_adoption_cancel_item()]},
                }
            ],
        )
    elif state == AdoptionDraftState.CHOOSING_PATH:
        # Same idea: 心有所屬／請推薦給我 are Rich Menu taps now, not chat buttons.
        await _reply(
            line,
            event,
            [
                {
                    "type": "text",
                    "text": "請從下方選單選擇領養方式。",
                    "quickReply": {
                        "items": [
                            _postback(
                                "返回地區選單", urlencode({"action": "back", "flow": "adoption"})
                            ),
                            _adoption_cancel_item(),
                        ]
                    },
                }
            ],
        )
    elif state == AdoptionDraftState.SELECTING_TARGET_ANIMAL:
        animals = await AnimalRepository(session, draft.organization_id).list_adoptable()
        if not animals:
            await _reply(line, event, [_text("目前沒有可領養的動物，請聯繫工作人員協助。")])
            return
        items = [
            _postback(
                f"{animal.name}／{animal.shelter_number or '無收容編號'}",
                urlencode(
                    {"action": "select_target_animal", "flow": "adoption", "value": str(animal.id)}
                ),
            )
            for animal in animals
        ][:10]
        items.append(_adoption_cancel_item())
        await _reply(
            line,
            event,
            [{"type": "text", "text": "請選擇想領養的動物。", "quickReply": {"items": items}}],
        )
    elif state == AdoptionDraftState.CONFIRMING_TARGET_ANIMAL:
        animal = await AnimalRepository(session, draft.organization_id).get(draft.target_animal_id)
        if animal is None:
            await _reply(line, event, [_text("動物資料異常，請重新選擇。")])
            return
        await _reply(
            line,
            event,
            await _animal_confirmation_messages(session, animal, draft.organization_id)
            + [
                _text(f"請確認：{animal.name}／{animal.shelter_number or '無收容編號'}"),
                {
                    "type": "template",
                    "altText": "確認動物",
                    "template": {
                        "type": "buttons",
                        "text": "是這隻動物嗎？",
                        "actions": [
                            _action(
                                "確認是這隻",
                                urlencode({"action": "confirm_target_animal", "flow": "adoption"}),
                            ),
                            _adoption_cancel_action(),
                        ],
                    },
                },
            ],
        )
    elif state in _ADOPTION_STATE_QUESTION_KEY:
        key = _ADOPTION_STATE_QUESTION_KEY[state]
        items = [
            _postback(label, urlencode({"action": "answer", "flow": "adoption", "value": code}))
            for code, label in _ADOPTION_QUESTION_OPTIONS[key]
        ]
        items.append(_adoption_cancel_item())
        await _reply(
            line,
            event,
            [
                {
                    "type": "text",
                    "text": f"請問{_ADOPTION_QUESTION_LABEL[key]}？",
                    "quickReply": {"items": items},
                }
            ],
        )
    elif state == AdoptionDraftState.SELECTING_MATCHED_ANIMAL:
        repository = AnimalRepository(session, draft.organization_id)
        cards = []
        for rank, result in enumerate(draft.match_results or [], start=1):
            animal = await repository.get(UUID(result["animal_id"]))
            if animal is None:
                continue
            cards.append(
                MatchReportCard(
                    animal_id=str(animal.id),
                    name=animal.name,
                    shelter_number=animal.shelter_number,
                    photo_url=await _animal_photo_url(draft.organization_id, animal),
                    score=result["score"],
                    reasons=tuple(result.get("reasons", [])),
                    rank=rank,
                    selectable=True,
                )
            )
        if not cards:
            await _reply(line, event, [_text("目前沒有符合條件的可領養動物，請聯繫工作人員協助。")])
            return
        await _reply(
            line,
            event,
            [
                _text("為你推薦以下毛孩，請選擇一隻："),
                build_match_report(cards),
                {
                    "type": "text",
                    "text": "若想重新開始，也可以取消這次媒合。",
                    "quickReply": {"items": [_adoption_cancel_item()]},
                },
            ],
        )
    elif state == AdoptionDraftState.AWAITING_PHONE_NUMBER:
        messages: list[dict] = []
        if draft.path == "specific_animal" and draft.match_results:
            result = draft.match_results[0]
            animal = await AnimalRepository(session, draft.organization_id).get(
                UUID(result["animal_id"])
            )
            if animal is not None:
                messages.append(
                    build_match_report(
                        [
                            MatchReportCard(
                                animal_id=str(animal.id),
                                name=animal.name,
                                shelter_number=animal.shelter_number,
                                photo_url=await _animal_photo_url(draft.organization_id, animal),
                                score=result["score"],
                                reasons=tuple(result.get("reasons", [])),
                            )
                        ]
                    )
                )
        messages.append(
            {
                "type": "text",
                "text": "請直接輸入您的手機號碼，方便工作人員與您聯絡（例如 0912345678）。",
                "quickReply": {"items": [_adoption_cancel_item()]},
            }
        )
        await _reply(line, event, messages)
    elif state == AdoptionDraftState.REVIEWING:
        summary_lines = [
            f"{_ADOPTION_QUESTION_LABEL.get(key, key)}：{value}"
            for key, value in draft.answers.items()
            if key != "phone_number"
        ]
        summary_lines.append(f"聯絡電話：{draft.answers.get('phone_number', '')}")
        await _reply(
            line,
            event,
            [
                _text("領養意願摘要：\n" + "\n".join(summary_lines) + "\n\n確認送出前仍可修改。"),
                {
                    "type": "template",
                    "altText": "領養意願確認",
                    "template": {
                        "type": "buttons",
                        "text": "領養意願摘要",
                        "actions": [
                            _action("送出", urlencode({"action": "submit", "flow": "adoption"})),
                            _action("取消", urlencode({"action": "cancel", "flow": "adoption"})),
                            _action("修改", urlencode({"action": "back", "flow": "adoption"})),
                        ],
                    },
                },
            ],
        )


async def _handle_adoption_postback(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    adopter_user_id: UUID,
    organization_id: UUID | None,
) -> None:
    values = parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True)
    action = values.get("action", [""])[0]
    value = values.get("value", [None])[0]
    repository = AdoptionDraftRepository(session, organization_id)

    if action == "start_adoption_matching":
        # Re-tapping the rich menu mid-conversation (e.g. the user got
        # distracted) must resume, not error — only create a fresh draft when
        # there truly isn't an active one yet.
        existing = await repository.get_active_for_adopter(adopter_user_id)
        if existing is not None:
            await _adoption_reply_for_state(session, line, event, draft=existing)
            return
        draft_service = LineAdoptionDraftService(
            repository, ttl_seconds=get_settings().draft_ttl_seconds
        )
        draft, _token = await draft_service.create(adopter_user_id=adopter_user_id)
        await _adoption_reply_for_state(session, line, event, draft=draft)
        return

    if action == "select_region":
        # A read-only "peek" action, like the volunteer flow's
        # list_reportable_animals — it doesn't touch the draft or state
        # machine at all, just answers with whatever's in that region.
        if not value:
            raise DomainError("region_required", "需要選擇地區", 422)
        organizations = await OrganizationRepository(session).list_with_adoptable_animals_by_region(
            value
        )
        if not organizations:
            await _reply(
                line,
                event,
                [_text("這個地區目前沒有開放領養媒合的收容所，請選擇其他地區或聯繫工作人員。")],
            )
            return
        cards = [
            ShelterCard(
                organization_id=str(organization.id),
                name=organization.name,
                service_area=organization.service_area,
                adoptable_count=count,
            )
            for organization, count in organizations
        ]
        await _reply(line, event, [build_shelter_carousel(cards)])
        return

    async def organization_validator(candidate_id: UUID) -> bool:
        organizations = await OrganizationRepository(session).list_with_adoptable_animals()
        return candidate_id in {organization.id for organization in organizations}

    conversation = LineAdoptionConversationService(
        repository,
        organization_validator=organization_validator,
        answer_validator=_adoption_answer_validator,
    )
    result = await conversation.handle(
        token=None,
        adopter_user_id=adopter_user_id,
        action=action,
        value=value,
        event_id=event.get("webhookEventId", ""),
    )
    if result.inquiry_id is not None:
        await _reply(line, event, [_text("已收到您的領養意願，收容所工作人員將盡快與您聯絡。")])
        await _revert_adoption_rich_menu(line, event)
        return
    if result.state in {AdoptionDraftState.CANCELLED, AdoptionDraftState.EXPIRED}:
        await _reply(line, event, [_text("已取消這次領養媒合對話。")])
        await _revert_adoption_rich_menu(line, event)
        return
    updated_draft = await repository.get_active_for_adopter(adopter_user_id)
    if updated_draft is not None:
        await _adoption_reply_for_state(session, line, event, draft=updated_draft)


async def _handle_adoption_text(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    adopter_user_id: UUID,
    organization_id: UUID | None,
    text: str,
) -> None:
    repository = AdoptionDraftRepository(session, organization_id)
    draft = await repository.get_active_for_adopter(adopter_user_id)
    if draft is None or draft.current_step != AdoptionDraftState.AWAITING_PHONE_NUMBER.value:
        await _reply(line, event, [_text("目前步驟請使用選單按鈕操作，不需要輸入文字。")])
        return
    conversation = LineAdoptionConversationService(
        repository, answer_validator=_adoption_answer_validator
    )
    await conversation.handle(
        token=None,
        adopter_user_id=adopter_user_id,
        action="phone_number",
        value=text,
        event_id=event.get("webhookEventId", ""),
    )
    updated_draft = await repository.get_active_for_adopter(adopter_user_id)
    if updated_draft is not None:
        await _adoption_reply_for_state(session, line, event, draft=updated_draft)


async def _resolve_growth_diary_pending(
    session, line_user_id: str
) -> tuple[UUID, GrowthDiaryDraft] | None:
    """Mirrors `_resolve_adoption_draft_context`'s peek-first shape: returns
    None for any LINE user with no binding or no pending diary entry, so
    every other flow (adoption, volunteer) falls through completely
    unaffected."""
    binding = await LineWebhookRepository(session).binding(line_user_id)
    if binding is None:
        return None
    draft = await get_pending_growth_diary_draft(session, binding.user_id)
    if draft is None:
        return None
    return binding.user_id, draft


async def _handle_growth_diary_postback(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    adopter_user_id: UUID,
    pending_draft: GrowthDiaryDraft | None,
) -> None:
    values = parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True)
    action = values.get("action", [""])[0]
    value = values.get("value", [None])[0]

    if action == "start_growth_diary":
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

    raise DomainError("invalid_postback_action", "目前步驟不允許此操作", 409)


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


async def _handle_growth_diary_message(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    adopter_user_id: UUID,
    pending_draft: GrowthDiaryDraft,
) -> None:
    message = event.get("message", {})
    message_type = message.get("type")

    if message_type == "text" and message.get("text", "").strip() == "取消":
        await clear_pending_growth_diary_draft(session, adopter_user_id)
        await _reply(line, event, [_text("已取消這次成長日記紀錄。")])
        return

    photo_key: str | None = None
    note: str | None = None
    if message_type == "image":
        try:
            content = await line.get_image_content(message_id=message["id"])
            photo_key = (
                f"growth-diary/{pending_draft.inquiry_id}/{event.get('webhookEventId', '')}.media"
            )
            await MediaProcessingService(MinioStorageAdapter()).store_cleaned(
                organization_id=pending_draft.organization_id,
                object_key=photo_key,
                data=content.content,
                declared_content_type=content.content_type,
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

    await GrowthDiaryRepository(session, pending_draft.organization_id).add_entry(
        inquiry_id=pending_draft.inquiry_id,
        animal_id=pending_draft.animal_id,
        adopter_user_id=adopter_user_id,
        photo_key=photo_key,
        note=note,
    )
    await clear_pending_growth_diary_draft(session, adopter_user_id)
    await _reply(line, event, [_text("已記錄毛孩的成長日記！感謝分享 🐾")])


async def _handle_postback(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    user_id: UUID,
    organization_id: UUID,
    membership_id: UUID,
) -> UUID | None:
    values = parse_qs(event.get("postback", {}).get("data", ""), keep_blank_values=True)
    action = values.get("action", [""])[0]
    if action in {"start_care_report", "list_reportable_animals"}:
        items = await _reportable_animals(session, organization_id, user_id)
        if not items:
            await _reply(line, event, [_text("今日目前沒有可回報的動物。")])
            return None
        await _reply(
            line,
            event,
            [{"type": "text", "text": "請選擇本次照護的動物。", "quickReply": {"items": items}}],
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
        items = await _reportable_animals(session, organization_id, user_id, draft_token=token)
        await _reply(
            line,
            event,
            [
                _text("請選擇要更換的動物；原有答案會保留但必須重新確認，照片不會沿用。"),
                {"type": "text", "text": "可回報動物", "quickReply": {"items": items}},
            ],
        )
        return None
    if action == "select_animal":
        animal_id = _uuid_value(values.get("animal_id", [""])[0])
        animal = (
            None
            if animal_id is None
            else await AnimalRepository(session, organization_id).get(animal_id)
        )
        if (
            animal is None
            or animal.status != "active"
            or not await ReportableScopeRepository(session, organization_id).is_animal_reportable(
                animal_id=animal.id, volunteer_user_id=user_id
            )
        ):
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        data = urlencode(
            {
                "action": "confirm_animal",
                "animal_id": str(animal.id),
                **({"draft_token": token} if token else {}),
            }
        )
        await _reply(
            line,
            event,
            await _animal_confirmation_messages(session, animal, organization_id)
            + [
                _text(f"請確認：{animal.name}／{animal.shelter_number or '無收容編號'}"),
                {
                    "type": "template",
                    "altText": "確認動物",
                    "template": {
                        "type": "buttons",
                        "text": "是這隻動物嗎？",
                        "actions": [_action("確認是這隻", data)],
                    },
                },
            ],
        )
        return None
    if action == "confirm_animal":
        animal_id = _uuid_value(values.get("animal_id", [""])[0])
        animal = (
            None
            if animal_id is None
            else await AnimalRepository(session, organization_id).get(animal_id)
        )
        if (
            animal is None
            or animal.status != "active"
            or not await ReportableScopeRepository(session, organization_id).is_animal_reportable(
                animal_id=animal.id, volunteer_user_id=user_id
            )
        ):
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        draft_service = LineDraftService(
            CareReportDraftRepository(session, organization_id),
            ttl_seconds=get_settings().draft_ttl_seconds,
        )
        if token:
            draft = await CareReportDraftRepository(session, organization_id).get_by_token(token)
            if draft is None or draft.volunteer_user_id != user_id or draft.status != "active":
                raise DomainError("draft_access_denied", "草稿不存在或無法存取", 404)
            await draft_service.begin_reselection(draft.id, candidate_animal_id=animal.id)
            await draft_service.confirm_reselection(draft.id)
            await CareReportDraftRepository(session, organization_id).clear_media(draft.id)
            raw_token = token
            message = f"已更換為 {animal.name}；原有答案需重新確認，照片不會沿用。"
        else:
            draft, raw_token = await draft_service.create(
                volunteer_user_id=user_id,
                membership_id=membership_id,
                animal_id=animal.id,
            )
            message = f"已確認 {animal.name}，現在開始照護回報。"
        await _reply(line, event, [_text(message)])
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=draft,
            raw_token=raw_token,
        )
        return None
    if action == "resume_draft" and not token:
        draft = await CareReportDraftRepository(session, organization_id).get_active_for_volunteer(
            user_id
        )
        if draft is None:
            await _reply(line, event, [_text("目前沒有可繼續的回報。")])
            return None
        await _reply(line, event, [_text("已恢復未完成回報，請繼續回答目前問題。")])
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=draft,
            raw_token="",
        )
        return None
    if not token and action not in {
        "answer",
        "back",
        "skip_media",
        "skip_note",
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
    if action in {"answer", "submit", "submit_current"}:
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
        await _reply(
            line, event, [_text("原始照護回報已保存。AI 分析將於背景處理，不會阻擋本次回報。")]
        )
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


@router.post("/webhook", openapi_extra={"security": []})
async def webhook(request: Request, x_line_signature: str | None = Header(default=None)) -> dict:
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

    # A local/demo channel access token (the ".env.example" placeholder) never
    # works against the real LINE API anyway, so route those requests to the
    # in-memory mock adapter instead and surface what it captured — this is
    # what lets `scripts/adoption_chat_demo.py` drive a real conversation
    # against this endpoint without a real LINE channel. Any real-looking
    # token (GCP demo, production) is untouched and still uses the real API.
    line = (
        MockLineAdapter()
        if settings.line_channel_access_token.startswith("fake-")
        else LineMessagingApiAdapter()
    )
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
            async with session.begin():
                identity = LineWebhookRepository(session)
                stored_event, claimed = await identity.claim_event(
                    webhook_event_id=event_id,
                    event_type=event.get("type", "unknown"),
                    redelivery=bool(event.get("deliveryContext", {}).get("isRedelivery")),
                )
                if not claimed:
                    results.append({"webhook_event_id": event_id, "status": "duplicate_ignored"})
                    continue
                is_adoption_flow = False
                try:
                    source = event.get("source", {})
                    line_user_id = source.get("userId")
                    if not line_user_id:
                        raise DomainError("line_user_missing", "LINE 使用者識別不存在", 403)
                    if await _handle_public_volunteer_application_entry(session, line, event):
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue

                    # Adopters never gain an OrganizationMembership, so they can
                    # never resolve through the membership-based _resolve_context
                    # below. Peek for an existing adoption draft (or a brand-new
                    # adoption entry postback) FIRST and short-circuit — every
                    # other event, including every existing volunteer action,
                    # falls through to the unchanged branches beneath completely
                    # unaffected. See adoption_matching plan §4 for the rationale.
                    adoption_context = await _resolve_adoption_draft_context(session, line_user_id)
                    adoption_entry_action = None
                    growth_diary_entry_action = None
                    if event.get("type") == "postback":
                        postback_values = parse_qs(
                            event.get("postback", {}).get("data", ""), keep_blank_values=True
                        )
                        flow_value = postback_values.get("flow", [""])[0]
                        if flow_value == "adoption":
                            adoption_entry_action = postback_values.get("action", [""])[0]
                        elif flow_value == "growth_diary":
                            growth_diary_entry_action = postback_values.get("action", [""])[0]

                    if adoption_context is not None:
                        is_adoption_flow = True
                        adopter_user_id, adoption_org_id = adoption_context
                        if event.get("type") == "postback":
                            await _handle_adoption_postback(
                                session,
                                line,
                                event,
                                adopter_user_id=adopter_user_id,
                                organization_id=adoption_org_id,
                            )
                        elif (
                            event.get("type") == "message"
                            and event.get("message", {}).get("type") == "text"
                        ):
                            await _handle_adoption_text(
                                session,
                                line,
                                event,
                                adopter_user_id=adopter_user_id,
                                organization_id=adoption_org_id,
                                text=event["message"].get("text", ""),
                            )
                        else:
                            await _reply(
                                line,
                                event,
                                [
                                    _text(
                                        "領養媒合請使用畫面上的選單按鈕操作，暫不支援這種訊息類型。"
                                    )
                                ],
                            )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue

                    growth_diary_pending = await _resolve_growth_diary_pending(
                        session, line_user_id
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
                    if adoption_entry_action == "start_adoption_matching":
                        is_adoption_flow = True
                        adopter_user_id = await _get_or_create_adopter_identity(
                            session, line_user_id
                        )
                        await _handle_adoption_postback(
                            session,
                            line,
                            event,
                            adopter_user_id=adopter_user_id,
                            organization_id=None,
                        )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue
                    if growth_diary_entry_action in {
                        "start_growth_diary",
                        "select_growth_diary_animal",
                    }:
                        # Never lazily create an identity here (unlike adoption
                        # entry) — if this LINE user has no binding at all, they
                        # cannot possibly have a completed AdoptionInquiry yet.
                        binding = await LineWebhookRepository(session).binding(line_user_id)
                        if binding is None:
                            await _reply(
                                line,
                                event,
                                [
                                    _text(
                                        "請先透過「領養媒合」完成一次領養意願，才能使用毛孩成長日記。"
                                    )
                                ],
                            )
                        else:
                            await _handle_growth_diary_postback(
                                session,
                                line,
                                event,
                                adopter_user_id=binding.user_id,
                                pending_draft=None,
                            )
                        await identity.complete_event(stored_event)
                        results.append({"webhook_event_id": event_id, "status": "processed"})
                        continue

                    user_id, organization_id, membership_id = await _resolve_context(
                        session, line_user_id
                    )
                    await _sync_volunteer_rich_menu(line, event)
                    if event.get("type") == "postback":
                        report_id_to_dispatch = await _handle_postback(
                            session,
                            line,
                            event,
                            user_id=user_id,
                            organization_id=organization_id,
                            membership_id=membership_id,
                        )
                    elif (
                        event.get("type") == "message"
                        and event.get("message", {}).get("type") == "text"
                    ):
                        draft_repository = CareReportDraftRepository(session, organization_id)
                        text_result = await LineDraftConversationService(draft_repository).handle(
                            token=None,
                            volunteer_user_id=user_id,
                            action="note",
                            value=event["message"].get("text", ""),
                            event_id=event_id,
                        )
                        report_id_to_dispatch = text_result.report_id
                        draft = await draft_repository.get_active_for_volunteer(user_id)
                        if draft is not None:
                            await _reply_next_step(
                                session,
                                line,
                                event,
                                organization_id=organization_id,
                                draft=draft,
                                raw_token="",
                            )
                    elif (
                        event.get("type") == "message"
                        and event.get("message", {}).get("type") == "image"
                    ):
                        draft = await CareReportDraftRepository(
                            session, organization_id
                        ).get_active_for_volunteer(user_id)
                        if draft is None or draft.current_step != DraftState.AWAITING_MEDIA.value:
                            raise DomainError("invalid_draft_step", "目前回報步驟不接受照片", 409)
                        try:
                            await LineImageService(line, MinioStorageAdapter()).attach_to_draft(
                                message_id=event["message"]["id"],
                                organization_id=organization_id,
                                object_key=f"drafts/{draft.id}/{event_id}.media",
                                draft_id=draft.id,
                                source_event_id=event_id,
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
                        draft.current_step = DraftState.AWAITING_NOTE.value
                        draft.last_interaction_at = datetime.now(timezone.utc)
                        await session.flush()
                        await _reply(line, event, [_text("照片已附加，請繼續完成回報。")])
                    await identity.complete_event(stored_event)
                    results.append({"webhook_event_id": event_id, "status": "processed"})
                except DomainError as error:
                    await identity.complete_event(
                        stored_event, status="failed", error_code=error.code
                    )
                    if is_adoption_flow and error.code == "draft_expired":
                        await _revert_adoption_rich_menu(line, event)
                    message = (
                        _liff_binding_message()
                        if error.code in {"line_binding_required", "shelter_context_required"}
                        else error.message
                    )
                    await _reply(line, event, [_text(message)])
                    results.append(
                        {"webhook_event_id": event_id, "status": "rejected", "reason": error.code}
                    )
            if report_id_to_dispatch is not None:
                await ReportJobDispatchService(session_factory).dispatch(
                    organization_id=organization_id,
                    report_id=report_id_to_dispatch,
                )
    response: dict = {"accepted": True, "event_results": results}
    if isinstance(line, MockLineAdapter):
        response["debug_replies"] = [messages for _token, messages in line.replies]
        response["debug_linked_menus"] = [
            {"rich_menu_id": rich_menu_id, "user_id": user_id}
            for rich_menu_id, user_id in line.linked_menus
        ]
    return response
