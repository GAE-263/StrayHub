from __future__ import annotations

# LINE message payloads intentionally mirror the Messaging API's nested JSON
# shape; E501 is suppressed for those literal payloads only.
# ruff: noqa: E501
import json
import logging
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import APIRouter, Header, Request
from services.api.app.api.errors import DomainError
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)
from services.api.app.application.line_draft_conversation import (
    LineDraftConversationService,
)
from services.api.app.application.line_draft_service import LineDraftService
from services.api.app.application.line_image_service import LineImageService
from services.api.app.application.line_message_presenter import (
    WOOD,
    WOOD_DEEP,
    celebration_bubble,
    prompt_bubble,
    question_bubble,
    summary_bubble,
)
from services.api.app.application.line_webhook_session import LineWebhookSessionService
from services.api.app.application.media_access import MediaAccessService
from services.api.app.application.ports.line_messaging import LineMessagingPort
from services.api.app.application.report_job_dispatch import ReportJobDispatchService
from services.api.app.config.settings import get_settings
from services.api.app.domain.line_care_report_state import (
    REQUIRED_ANSWER_KEYS,
    DraftAnswers,
    DraftState,
    DraftStateMachine,
)
from services.api.app.domain.line_webhook_security import verify_line_signature
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.shelter_area import ShelterArea
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.line_webhook_repository import LineWebhookRepository
from services.api.app.persistence.repositories.observation_repository import ObservationRepository
from services.api.app.persistence.repositories.reportable_scope_repository import (
    ReportableScopeRepository,
)
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/line", tags=["LINE Bot"])


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


def _postback_action(label: str, data: str, *, display_text: str | None = None) -> dict:
    """A bare action object, as required by a template's ``actions`` list."""
    return {
        "type": "postback",
        "label": label[:20],
        "data": data,
        "displayText": display_text or label,
    }


def _postback(label: str, data: str, *, display_text: str | None = None) -> dict:
    """A quick reply item, which wraps the action in an ``action`` envelope."""
    return {
        "type": "action",
        "action": _postback_action(label, data, display_text=display_text),
    }


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


# The answer key and its CRM category code agree everywhere except walk.
_ANSWER_CATEGORY_CODES = {"walk_reaction": "walk"}

# Decorative only. The heading text itself still comes from the CRM vocabulary;
# these just give each question a recognisable face in the chat.
_CATEGORY_GLYPHS = {
    "care_completion": "🧺",
    "walk_completion": "🚶",
    "feeding": "🍚",
    "water": "💧",
    "activity": "⚡",
    "urination": "💦",
    "defecation": "💩",
    "resource_guarding": "🦴",
    "human_interaction": "🤝",
    "animal_interaction": "🐕",
    "emotion": "💚",
    "walk": "🌿",
    "appearance_special_status": "🔍",
}


def _glyph_for(key: str) -> str:
    return _CATEGORY_GLYPHS.get(_ANSWER_CATEGORY_CODES.get(key, key), "🐾")


def _current_answer_key(state: DraftState, answers: dict, reconfirmation_keys) -> str:
    return DraftStateMachine(
        state=state,
        answers=DraftAnswers(dict(answers)),
        reconfirmation_keys=set(reconfirmation_keys or []),
    ).next_answer_key()


async def _category_titles(session, organization_id: UUID) -> dict[str, str]:
    """Question headings come from the CRM vocabulary, never from a local copy."""
    categories = await ObservationRepository(session, organization_id).categories()
    return {category.code: category.display_name for category in categories}


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


async def _reply_next_step(
    session,
    line: LineMessagingPort,
    event: dict,
    *,
    organization_id: UUID,
    draft,
    raw_token: str,
    prefix_messages: list[dict] | None = None,
) -> None:
    # A LINE reply token may be used exactly once, so a caller that wants to say
    # something before the next step must pass it as prefix_messages rather than
    # issuing its own reply; a second reply on the same event is rejected with
    # "Invalid reply token".
    messages: list[dict] = list(prefix_messages or [])
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
        reconfirmation_keys = getattr(draft, "reconfirmation_keys", None)
        options = await _answer_options(
            session, organization_id, state, draft.answers, reconfirmation_keys
        )
        key = _current_answer_key(state, draft.answers, reconfirmation_keys)
        titles = await _category_titles(session, organization_id)
        messages.append(
            question_bubble(
                options,
                draft_token=raw_token,
                step=state.value,
                title=titles.get(_ANSWER_CATEGORY_CODES.get(key, key), key),
                position=REQUIRED_ANSWER_KEYS.index(key) + 1,
                total=len(REQUIRED_ANSWER_KEYS),
                glyph=_glyph_for(key),
            )
        )
    elif state == DraftState.AWAITING_MEDIA:
        messages.append(
            prompt_bubble(
                title="拍一張今天的牠",
                caption="照護回報 · 選填",
                body_text="直接在聊天室傳照片就可以了，想傳幾張都行 📷\n沒拍到也沒關係，按略過就好。",
                glyph="📸",
                choices=[
                    ("略過照片", f"action=skip_media&draft_token={raw_token}", "⏭"),
                    ("上一步", f"action=back&draft_token={raw_token}", "←"),
                ],
            )
        )
    elif state == DraftState.AWAITING_NOTE:
        messages.append(
            prompt_bubble(
                title="今天有什麼想說的嗎",
                caption="照護回報 · 選填",
                body_text="想補充的事情直接打字傳過來就好 ✏️\n例如今天特別黏人、或是走路好像怪怪的。",
                glyph="💭",
                start=WOOD,
                end=WOOD_DEEP,
                choices=[
                    ("略過心得", f"action=skip_note&draft_token={raw_token}", "⏭"),
                    ("上一步", f"action=back&draft_token={raw_token}", "←"),
                ],
            )
        )
    elif state == DraftState.REVIEWING:
        review_options = await ObservationRepository(session, organization_id).effective_options(
            include_disabled_history=True
        )
        labels = {option.code: option.display_name for option in review_options}
        titles = await _category_titles(session, organization_id)
        rows = [
            (
                _glyph_for(key),
                titles.get(_ANSWER_CATEGORY_CODES.get(key, key), key),
                labels.get(value, value),
            )
            for key, value in draft.answers.items()
        ]
        animal = await AnimalRepository(session, organization_id).get(draft.animal_id)
        messages.append(
            summary_bubble(
                rows,
                note=draft.note,
                animal_name=animal.name if animal is not None else "",
                choices=[
                    (
                        "送出回報",
                        f"action={'submit' if raw_token else 'submit_current'}"
                        f"&draft_token={raw_token}",
                        "✅",
                    ),
                    ("再改一下", f"action=back&draft_token={raw_token}", "✏️"),
                    ("換一隻", f"action=reselect_animal&draft_token={raw_token}", "🔄"),
                    (
                        "取消回報",
                        f"action={'cancel' if raw_token else 'cancel_current'}"
                        f"&draft_token={raw_token}",
                        "🗑",
                    ),
                ],
            )
        )
    if messages:
        await _reply(line, event, messages)


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
                        "actions": [_postback_action("確認是這隻", data)],
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
            # A new draft starts in CONFIRMING_ANIMAL; advance it so the reply
            # below carries the first question instead of stalling here.
            await LineDraftConversationService(
                CareReportDraftRepository(session, organization_id)
            ).handle(
                token=raw_token,
                volunteer_user_id=user_id,
                action="confirm_animal",
                value=None,
                event_id=event.get("webhookEventId", ""),
            )
            message = f"已確認 {animal.name}，現在開始照護回報。"
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=draft,
            raw_token=raw_token,
            prefix_messages=[_text(message)],
        )
        return None
    if action == "resume_draft" and not token:
        draft = await CareReportDraftRepository(session, organization_id).get_active_for_volunteer(
            user_id
        )
        if draft is None:
            await _reply(line, event, [_text("目前沒有可繼續的回報。")])
            return None
        await _reply_next_step(
            session,
            line,
            event,
            organization_id=organization_id,
            draft=draft,
            raw_token="",
            prefix_messages=[_text("已恢復未完成回報，請繼續回答目前問題。")],
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
        animal = await AnimalRepository(session, organization_id).get(draft.animal_id)
        await _reply(
            line,
            event,
            [celebration_bubble(animal_name=animal.name if animal is not None else "")],
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


@router.post("/webhook")
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

    line = LineMessagingApiAdapter()
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
                try:
                    source = event.get("source", {})
                    line_user_id = source.get("userId")
                    if not line_user_id:
                        raise DomainError("line_user_missing", "LINE 使用者識別不存在", 403)
                    user_id, organization_id, membership_id = await _resolve_context(
                        session, line_user_id
                    )
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
                            # The volunteer only ever sees "try again or skip",
                            # so the cause has to be recorded here or it is lost.
                            logger.exception(
                                "draft media attach failed for draft %s: %s",
                                draft.id,
                                error_code,
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
                        # Carry on to the note step in the same reply; otherwise
                        # the volunteer is left with no control to continue.
                        await _reply_next_step(
                            session,
                            line,
                            event,
                            organization_id=organization_id,
                            draft=draft,
                            raw_token="",
                            prefix_messages=[_text("照片已附加。")],
                        )
                    await identity.complete_event(stored_event)
                    results.append({"webhook_event_id": event_id, "status": "processed"})
                except DomainError as error:
                    await identity.complete_event(
                        stored_event, status="failed", error_code=error.code
                    )
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
    return {"accepted": True, "event_results": results}
