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
from services.api.app.application.line_draft_conversation import (
    LineDraftConversationService,
)
from services.api.app.application.line_draft_service import LineDraftService
from services.api.app.application.line_image_service import LineImageService
from services.api.app.application.line_message_presenter import quick_reply_for_options
from services.api.app.application.line_webhook_session import LineWebhookSessionService
from services.api.app.application.media_access import MediaAccessService
from services.api.app.application.ports.line_messaging import LineMessagingPort
from services.api.app.application.report_job_dispatch import ReportJobDispatchService
from services.api.app.config.settings import get_settings
from services.api.app.domain.line_care_report_state import (
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
                            _postback("略過照片", f"action=skip_media&draft_token={raw_token}"),
                            _postback("上一步", f"action=back&draft_token={raw_token}"),
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
                            _postback("略過心得", f"action=skip_note&draft_token={raw_token}"),
                            _postback("上一步", f"action=back&draft_token={raw_token}"),
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
                            _postback(
                                "送出回報",
                                f"action={'submit' if raw_token else 'submit_current'}&draft_token={raw_token}",
                            ),
                            _postback(
                                "取消回報",
                                f"action={'cancel' if raw_token else 'cancel_current'}&draft_token={raw_token}",
                            ),
                            _postback(
                                "修改",
                                f"action=back&draft_token={raw_token}",
                            ),
                            _postback(
                                "更換動物",
                                f"action=reselect_animal&draft_token={raw_token}",
                            ),
                        ],
                    },
                },
            ],
        )


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
                        "actions": [_postback("確認是這隻", data)],
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
