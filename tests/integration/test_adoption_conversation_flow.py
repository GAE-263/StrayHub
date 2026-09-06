from __future__ import annotations

import json
import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.api.line_webhook import _adoption_answer_validator
from services.api.app.application.line_adoption_conversation import (
    LineAdoptionConversationService,
)
from services.api.app.application.line_adoption_draft_service import LineAdoptionDraftService
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
)
from services.api.app.persistence.repositories.adoption_inquiry_repository import (
    AdoptionInquiryRepository,
)


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


async def _insert_fixtures(*, organization_id, adopter_id, animal_ids) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Adoption Test Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"ADOPT-{organization_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Adoption Test Adopter', 'active', now(), now())
            """,
            adopter_id,
            f"adopter-{adopter_id.hex[:10]}",
        )
        for animal_id, name, size, energy, temperament in animal_ids:
            await connection.execute(
                """
                INSERT INTO animals
                    (id, organization_id, name, status, is_adoptable, size, energy,
                     temperament, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', true, $4, $5, $6::jsonb, now(), now())
                """,
                animal_id,
                organization_id,
                name,
                size,
                energy,
                json.dumps(list(temperament)),
            )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


async def _cleanup(*, organization_id, adopter_id) -> None:
    cleanup = await asyncpg.connect(_database_url())
    try:
        await cleanup.execute("BEGIN")
        await cleanup.execute(
            "DELETE FROM audit_records WHERE organization_id = $1", organization_id
        )
        await cleanup.execute(
            "DELETE FROM adoption_inquiries WHERE organization_id = $1", organization_id
        )
        await cleanup.execute(
            "DELETE FROM adoption_drafts WHERE organization_id = $1 OR adopter_user_id = $2",
            organization_id,
            adopter_id,
        )
        await cleanup.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        await cleanup.execute("DELETE FROM users WHERE id = $1", adopter_id)
        await cleanup.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await cleanup.execute("COMMIT")
    finally:
        await cleanup.close()


@pytest.mark.asyncio
async def test_recommend_me_path_matches_and_submits_inquiry() -> None:
    organization_id, adopter_id = uuid4(), uuid4()
    await engine.dispose(close=False)
    small_low = uuid4()
    medium_high = uuid4()
    try:
        await _insert_fixtures(
            organization_id=organization_id,
            adopter_id=adopter_id,
            animal_ids=[
                (small_low, "小安", "small", "low", []),
                (medium_high, "大力", "medium", "high", ["cat_ok"]),
            ],
        )

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                # A brand-new adopter has no organization yet, matching the real
                # SELECTING_ORGANIZATION entry point (Phase 4's webhook layer will
                # drive that step); create the draft unscoped, then simulate the
                # org having just been resolved before re-scoping the repository.
                unscoped_repository = AdoptionDraftRepository(session, None)
                draft_service = LineAdoptionDraftService(unscoped_repository, ttl_seconds=3600)
                draft, token = await draft_service.create(adopter_user_id=adopter_id)
                await draft_service.set_organization(draft.id, organization_id=organization_id)
                await session.flush()

                repository = AdoptionDraftRepository(session, organization_id)
                conversation = LineAdoptionConversationService(repository)
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="choose_path",
                    value="recommend_me",
                    event_id="e-choose-path",
                )
                # Skip the free-text self-introduction step (方向 D) and
                # fall back to the one-by-one questions this test exercises
                # directly below.
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="finish_freetext_profile",
                    value=None,
                    event_id="e-finish-freetext",
                )
                for index, value in enumerate(
                    [
                        "house",
                        "experienced",
                        "has_cats",
                        "adults_only",
                        "retired",
                        "structured",
                        "high_patience",
                        "companionship",
                        "medium",
                        "high",
                    ]
                ):
                    result = await conversation.handle(
                        token=token,
                        adopter_user_id=adopter_id,
                        action="answer",
                        value=value,
                        event_id=f"e-answer-{index}",
                    )

                # PRESENTING_MATCHES pauses at AWAITING_AI_RECOMMENDATIONS for
                # the AI background task to rerank the rule-based pool (see
                # line_webhook.py) — simulated here directly since that task
                # itself isn't exercised at this layer.
                assert result.state == AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS
                assert result.candidate_match_ids[0] == medium_high
                pending_draft = await repository.get_by_token(token)
                pending_draft.current_step = AdoptionDraftState.SELECTING_MATCHED_ANIMAL.value
                await session.flush()

                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="select_matched_animal",
                    value=str(medium_high),
                    event_id="e-select-match",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_target_animal",
                    value=None,
                    event_id="e-confirm-target",
                )
                # 留下聯絡方式現在拆成三步：姓名 → 方便聯繫時間 → 手機號碼。
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="王小明",
                    event_id="e-adopter-name",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="平日白天（9-18點）",
                    event_id="e-contact-time",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="phone_number",
                    value="0912345678",
                    event_id="e-phone",
                )
                submit_result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="submit",
                    value=None,
                    event_id="e-submit",
                )

                assert submit_result.state == AdoptionDraftState.SUBMITTED
                assert submit_result.inquiry_id is not None

                inquiry = await AdoptionInquiryRepository(session, organization_id).get(
                    submit_result.inquiry_id
                )
                assert inquiry is not None
                assert inquiry.target_animal_id == medium_high
                assert inquiry.phone_number == "0912345678"
                assert inquiry.status == "new"
    finally:
        await _cleanup(organization_id=organization_id, adopter_id=adopter_id)


@pytest.mark.asyncio
async def test_specific_animal_path_skips_matching_and_submits_inquiry() -> None:
    organization_id, adopter_id = uuid4(), uuid4()
    await engine.dispose(close=False)
    target_animal_id = uuid4()
    try:
        await _insert_fixtures(
            organization_id=organization_id,
            adopter_id=adopter_id,
            animal_ids=[(target_animal_id, "旺財", "large", "medium", [])],
        )

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                unscoped_repository = AdoptionDraftRepository(session, None)
                draft_service = LineAdoptionDraftService(unscoped_repository, ttl_seconds=3600)
                draft, token = await draft_service.create(adopter_user_id=adopter_id)
                await draft_service.set_organization(draft.id, organization_id=organization_id)
                await session.flush()

                repository = AdoptionDraftRepository(session, organization_id)
                conversation = LineAdoptionConversationService(repository)
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="choose_path",
                    value="specific_animal",
                    event_id="e-choose-path",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="select_target_animal",
                    value=str(target_animal_id),
                    event_id="e-select-target",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_target_animal",
                    value=None,
                    event_id="e-confirm-target",
                )
                # Skip the free-text self-introduction step (方向 D) and
                # fall back to the one-by-one questions this test exercises
                # directly below.
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="finish_freetext_profile",
                    value=None,
                    event_id="e-finish-freetext",
                )
                for index, value in enumerate(
                    [
                        "house",
                        "first_time",
                        "none",
                        "adults_only",
                        "work_from_home",
                        "structured",
                        "high_patience",
                        "companionship",
                    ]
                ):
                    result = await conversation.handle(
                        token=token,
                        adopter_user_id=adopter_id,
                        action="answer",
                        value=value,
                        event_id=f"e-answer-{index}",
                    )
                assert result.state == AdoptionDraftState.CONFIRMING_ANSWERS

                result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_answers",
                    value=None,
                    event_id="e-confirm-answers",
                )
                assert result.state == AdoptionDraftState.AWAITING_AI_SUITABILITY

                # In production this next hop is driven by the AI background
                # task itself (see line_webhook.py), not a user action. We
                # also stamp the score/explanation it would have written, to
                # verify submit() copies them onto the AdoptionInquiry below.
                pending_draft = await repository.get_by_token(token)
                pending_draft.current_step = AdoptionDraftState.AWAITING_ADOPTER_NAME.value
                pending_draft.ai_suitability_score = 82
                pending_draft.ai_suitability_explanation = "個性穩定，跟家庭步調很合拍"
                await session.flush()

                # 留下聯絡方式現在拆成三步：姓名 → 方便聯繫時間 → 手機號碼。
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="王小明",
                    event_id="e-adopter-name",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="平日白天（9-18點）",
                    event_id="e-contact-time",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="phone_number",
                    value="0987654321",
                    event_id="e-phone",
                )
                submit_result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="submit",
                    value=None,
                    event_id="e-submit",
                )

                assert submit_result.state == AdoptionDraftState.SUBMITTED
                inquiry = await AdoptionInquiryRepository(session, organization_id).get(
                    submit_result.inquiry_id
                )
                assert inquiry is not None
                assert inquiry.target_animal_id == target_animal_id
                assert inquiry.path == "specific_animal"
                # No candidate pool is ranked on this path, but the target
                # animal is still scored against the collected preferences so
                # the LINE report card has something to show.
                snapshot = inquiry.match_scores_snapshot
                assert snapshot == [
                    {"animal_id": str(target_animal_id), "score": 0.0, "reasons": []}
                ]
                # The AI suitability score/explanation the background task
                # wrote onto the draft must be copied onto the inquiry at
                # submit time — see AdoptionInquirySubmissionService.submit().
                assert inquiry.ai_suitability_score == 82
                assert inquiry.ai_suitability_explanation == "個性穩定，跟家庭步調很合拍"
    finally:
        await _cleanup(organization_id=organization_id, adopter_id=adopter_id)


@pytest.mark.asyncio
async def test_entered_awaiting_ai_suitability_fires_only_on_the_transition_edge() -> None:
    """`entered_awaiting_ai_suitability` gates the AI suitability analysis
    background task (see line_webhook.py) — it must be True only on the one
    `handle()` call that actually moves the draft into that state (the
    confirm_answers action out of CONFIRMING_ANSWERS), not on any other
    call, so the analysis fires exactly once per draft."""
    organization_id, adopter_id = uuid4(), uuid4()
    await engine.dispose(close=False)
    target_animal_id = uuid4()
    try:
        await _insert_fixtures(
            organization_id=organization_id,
            adopter_id=adopter_id,
            animal_ids=[(target_animal_id, "旺財", "large", "medium", [])],
        )

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                unscoped_repository = AdoptionDraftRepository(session, None)
                draft_service = LineAdoptionDraftService(unscoped_repository, ttl_seconds=3600)
                draft, token = await draft_service.create(adopter_user_id=adopter_id)
                await draft_service.set_organization(draft.id, organization_id=organization_id)
                await session.flush()

                repository = AdoptionDraftRepository(session, organization_id)
                conversation = LineAdoptionConversationService(repository)
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="choose_path",
                    value="specific_animal",
                    event_id="e-choose-path",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="select_target_animal",
                    value=str(target_animal_id),
                    event_id="e-select-target",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_target_animal",
                    value=None,
                    event_id="e-confirm-target",
                )
                # Skip the free-text self-introduction step (方向 D) and
                # fall back to the one-by-one questions this test exercises
                # directly below.
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="finish_freetext_profile",
                    value=None,
                    event_id="e-finish-freetext",
                )
                for index, value in enumerate(
                    ["house", "first_time", "none", "adults_only", "work_from_home"]
                ):
                    result = await conversation.handle(
                        token=token,
                        adopter_user_id=adopter_id,
                        action="answer",
                        value=value,
                        event_id=f"e-answer-{index}",
                    )
                    assert result.entered_awaiting_ai_suitability is False

                result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="structured",
                    event_id="e-answer-parenting-style",
                )
                assert result.entered_awaiting_ai_suitability is False

                result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="high_patience",
                    event_id="e-answer-patience",
                )
                assert result.entered_awaiting_ai_suitability is False

                # The last personality question transitions into the explicit
                # confirmation checkpoint.
                result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="companionship",
                    event_id="e-answer-motivation",
                )
                assert result.state == AdoptionDraftState.CONFIRMING_ANSWERS
                assert result.entered_awaiting_ai_suitability is False

                result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_answers",
                    value=None,
                    event_id="e-confirm-answers",
                )
                assert result.state == AdoptionDraftState.AWAITING_AI_SUITABILITY
                assert result.entered_awaiting_ai_suitability is True

                # A later call that moves the draft on from here (in
                # production, the AI background task doing so directly) must
                # not report the entering edge again.
                pending_draft = await repository.get_by_token(token)
                pending_draft.current_step = AdoptionDraftState.AWAITING_ADOPTER_NAME.value
                await session.flush()
                result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="王小明",
                    event_id="e-adopter-name",
                )
                assert result.entered_awaiting_ai_suitability is False
                result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="平日白天（9-18點）",
                    event_id="e-contact-time",
                )
                assert result.entered_awaiting_ai_suitability is False
                result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="phone_number",
                    value="0912345678",
                    event_id="e-phone",
                )
                assert result.state == AdoptionDraftState.REVIEWING
                assert result.entered_awaiting_ai_suitability is False
    finally:
        await _cleanup(organization_id=organization_id, adopter_id=adopter_id)


@pytest.mark.asyncio
async def test_back_to_selecting_organization_clears_organization_so_it_can_be_reselected() -> None:
    """Regression test: backing all the way out to SELECTING_ORGANIZATION
    must clear `draft.organization_id` too, not just the state-machine's own
    `path`/`target_animal_id` — otherwise re-picking a shelter (even the same
    one) hits `organization_already_selected`. Caught live via 返回地區選單.

    Uses token=None throughout (adopter_user_id-based lookup), matching how
    `_handle_adoption_postback` actually drives this service in production —
    that's where the bug was found; the token-based flow exercised by the
    other tests in this file is a separate (shelter-fixed) entry point that
    never revisits SELECTING_ORGANIZATION."""
    organization_id, adopter_id = uuid4(), uuid4()
    await engine.dispose(close=False)
    try:
        await _insert_fixtures(
            organization_id=organization_id, adopter_id=adopter_id, animal_ids=[]
        )

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                unscoped_repository = AdoptionDraftRepository(session, None)
                draft_service = LineAdoptionDraftService(unscoped_repository, ttl_seconds=3600)
                draft, _token = await draft_service.create(adopter_user_id=adopter_id)
                await draft_service.set_organization(draft.id, organization_id=organization_id)
                await session.flush()

                repository = AdoptionDraftRepository(session, organization_id)
                conversation = LineAdoptionConversationService(repository)
                await conversation.handle(
                    token=None,
                    adopter_user_id=adopter_id,
                    action="choose_path",
                    value="specific_animal",
                    event_id="e-choose-path",
                )

                result = await conversation.handle(
                    token=None,
                    adopter_user_id=adopter_id,
                    action="back",
                    value=None,
                    event_id="e-back-1",
                )
                assert result.state == AdoptionDraftState.CHOOSING_PATH

                result = await conversation.handle(
                    token=None,
                    adopter_user_id=adopter_id,
                    action="back",
                    value=None,
                    event_id="e-back-2",
                )
                assert result.state == AdoptionDraftState.SELECTING_ORGANIZATION

                refreshed = await repository.get_active_for_adopter(adopter_id)
                assert refreshed.organization_id is None

                # Re-selecting a shelter (even the same one) must succeed now.
                await conversation.handle(
                    token=None,
                    adopter_user_id=adopter_id,
                    action="select_organization",
                    value=str(organization_id),
                    event_id="e-reselect-org",
                )
                refreshed = await repository.get_active_for_adopter(adopter_id)
                assert refreshed.organization_id == organization_id
    finally:
        await _cleanup(organization_id=organization_id, adopter_id=adopter_id)


@pytest.mark.asyncio
async def test_choose_path_is_idempotent_against_a_duplicate_tap() -> None:
    """Regression test: LINE can redeliver a postback, or an adopter can tap
    a still-visible rich-menu/quick-reply button again before the first
    reply has rendered — a second identical choose_path call must not blow
    up. Reported live as "不允許的草稿狀態轉移" after tapping 推薦名單:
    choose_path() only knows how to fire from CHOOSING_PATH itself, so a
    second call (draft already past it) hit transition()'s generic
    mismatch error even though the adopter's actual intent was already
    satisfied the first time."""
    organization_id, adopter_id = uuid4(), uuid4()
    await engine.dispose(close=False)
    try:
        await _insert_fixtures(
            organization_id=organization_id, adopter_id=adopter_id, animal_ids=[]
        )

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                unscoped_repository = AdoptionDraftRepository(session, None)
                draft_service = LineAdoptionDraftService(unscoped_repository, ttl_seconds=3600)
                draft, _token = await draft_service.create(adopter_user_id=adopter_id)
                await draft_service.set_organization(draft.id, organization_id=organization_id)
                await session.flush()

                repository = AdoptionDraftRepository(session, organization_id)
                conversation = LineAdoptionConversationService(repository)
                first = await conversation.handle(
                    token=None,
                    adopter_user_id=adopter_id,
                    action="choose_path",
                    value="recommend_me",
                    event_id="e-choose-path-1",
                )
                assert first.state == AdoptionDraftState.AWAITING_FREETEXT_PROFILE

                # The duplicate tap: same path, same (already-moved-on) draft.
                second = await conversation.handle(
                    token=None,
                    adopter_user_id=adopter_id,
                    action="choose_path",
                    value="recommend_me",
                    event_id="e-choose-path-2",
                )
                assert second.state == AdoptionDraftState.AWAITING_FREETEXT_PROFILE

                refreshed = await repository.get_active_for_adopter(adopter_id)
                assert refreshed.path == "recommend_me"

                # Choosing a genuinely different path after one is already
                # committed is still rejected, not silently swapped.
                with pytest.raises(DomainError, match="不允許的草稿狀態轉移"):
                    await conversation.handle(
                        token=None,
                        adopter_user_id=adopter_id,
                        action="choose_path",
                        value="specific_animal",
                        event_id="e-choose-path-different",
                    )
    finally:
        await _cleanup(organization_id=organization_id, adopter_id=adopter_id)


@pytest.mark.asyncio
async def test_duplicate_answer_tap_on_the_last_question_is_idempotent() -> None:
    """Regression test: reported live as answering the last questionnaire
    question ("領養動機"/adoption_motivation, which the adopter had already
    supplied via free-text and the AI had genuinely picked up) landing on
    "目前步驟已完成" with nothing happening next.

    Root cause: `next_answer_key()` — reached via the `answer` action's own
    validator call — has no idea a duplicate/near-simultaneous second tap on
    the same button already answered this exact question in the first call;
    AdoptionDraftRepository's FOR UPDATE lock now serializes such taps
    instead of racing (see the earlier "目前步驟已完成" investigation), but
    the second, now-correctly-ordered call still hit that same error. This
    mirrors test_choose_path_is_idempotent_against_a_duplicate_tap's fix for
    the same duplicate-tap shape on a different action."""
    organization_id, adopter_id = uuid4(), uuid4()
    await engine.dispose(close=False)
    target_animal_id = uuid4()
    try:
        await _insert_fixtures(
            organization_id=organization_id,
            adopter_id=adopter_id,
            animal_ids=[(target_animal_id, "旺財", "large", "medium", [])],
        )

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                unscoped_repository = AdoptionDraftRepository(session, None)
                draft_service = LineAdoptionDraftService(unscoped_repository, ttl_seconds=3600)
                draft, token = await draft_service.create(adopter_user_id=adopter_id)
                await draft_service.set_organization(draft.id, organization_id=organization_id)
                await session.flush()

                repository = AdoptionDraftRepository(session, organization_id)
                conversation = LineAdoptionConversationService(repository)
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="choose_path",
                    value="specific_animal",
                    event_id="e-choose-path",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="select_target_animal",
                    value=str(target_animal_id),
                    event_id="e-select-target",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="confirm_target_animal",
                    value=None,
                    event_id="e-confirm-target",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="finish_freetext_profile",
                    value=None,
                    event_id="e-finish-freetext",
                )
                for index, value in enumerate(
                    [
                        "house",
                        "first_time",
                        "none",
                        "adults_only",
                        "work_from_home",
                        "structured",
                        "high_patience",
                    ]
                ):
                    result = await conversation.handle(
                        token=token,
                        adopter_user_id=adopter_id,
                        action="answer",
                        value=value,
                        event_id=f"e-answer-{index}",
                    )
                assert result.state == AdoptionDraftState.ANSWERING_ADOPTION_MOTIVATION

                # First tap on the last question: answers it and transitions.
                first = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="companionship",
                    event_id="e-answer-motivation-1",
                )
                assert first.state == AdoptionDraftState.CONFIRMING_ANSWERS

                # Duplicate tap on the very same (now stale) button — must not
                # raise, and must reflect the draft's real, already-advanced
                # state rather than erroring with nothing to show for it.
                second = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="companionship",
                    event_id="e-answer-motivation-2",
                )
                assert second.state == AdoptionDraftState.CONFIRMING_ANSWERS

                refreshed = await repository.get_by_token(token)
                assert refreshed.answers["adoption_motivation"] == "companionship"
                assert refreshed.current_step == AdoptionDraftState.CONFIRMING_ANSWERS.value
    finally:
        await _cleanup(organization_id=organization_id, adopter_id=adopter_id)


@pytest.mark.asyncio
async def test_answer_tap_for_a_question_already_filled_by_extraction_is_idempotent() -> None:
    """Regression test: reported live on 推薦名單 as "不支援的領養問卷答案：
    preferred_size" with nothing happening next, after answering
    「領養動機」normally (one question at a time, no double-tap).

    Root cause: free-text extraction can fill a *later* field (e.g.
    preferred_energy) while an *earlier* one (adoption_motivation) is still
    missing — skip_prefilled_questions() correctly parks the draft at
    ANSWERING_PREFERENCE_ADOPTION_MOTIVATION either way. If something else
    (a slow-to-land extraction round, or a duplicate tap that won a race)
    fills adoption_motivation between the adopter seeing that card and
    tapping an option on it, the "answer" branch's own skip_prefilled_
    questions() call (added for the choose_path/duplicate-tap fix) correctly
    advances past it to the next real question (preferred_size) — but then
    validated the *stale* tapped value ("companionship", meant for
    adoption_motivation) against preferred_size's options and blew up.
    Mirrors test_duplicate_answer_tap_on_the_last_question_is_idempotent's
    shape, but for a mismatched value rather than a repeated one."""
    organization_id, adopter_id = uuid4(), uuid4()
    await engine.dispose(close=False)
    try:
        await _insert_fixtures(
            organization_id=organization_id, adopter_id=adopter_id, animal_ids=[]
        )

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                unscoped_repository = AdoptionDraftRepository(session, None)
                draft_service = LineAdoptionDraftService(unscoped_repository, ttl_seconds=3600)
                draft, token = await draft_service.create(adopter_user_id=adopter_id)
                await draft_service.set_organization(draft.id, organization_id=organization_id)
                await session.flush()

                repository = AdoptionDraftRepository(session, organization_id)
                # answer_validator wired in, matching how line_webhook.py
                # actually constructs this service in production — without
                # it, an invalid value like "companionship" for
                # preferred_size would just be accepted as a raw string
                # rather than exercising the bug this test targets.
                conversation = LineAdoptionConversationService(
                    repository, answer_validator=_adoption_answer_validator
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="choose_path",
                    value="recommend_me",
                    event_id="e-choose-path",
                )
                await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="finish_freetext_profile",
                    value=None,
                    event_id="e-finish-freetext",
                )
                for index, value in enumerate(
                    [
                        "house",
                        "experienced",
                        "has_cats",
                        "adults_only",
                        "retired",
                        "free",
                        "medium_patience",
                    ]
                ):
                    result = await conversation.handle(
                        token=token,
                        adopter_user_id=adopter_id,
                        action="answer",
                        value=value,
                        event_id=f"e-answer-{index}",
                    )
                assert result.state == AdoptionDraftState.ANSWERING_PREFERENCE_ADOPTION_MOTIVATION

                # Simulates a race: something else (a slow extraction round,
                # or a duplicate tap that already won) fills the very
                # question the adopter is about to answer, without the
                # adopter's own draft view knowing about it yet.
                draft_row = await repository.get_by_token(token)
                draft_row.answers = {
                    **draft_row.answers,
                    "adoption_motivation": "companionship",
                }
                await session.flush()

                # The adopter's tap, meant for 領養動機, arrives after the
                # fact — its value doesn't apply to whatever question is
                # genuinely still pending (preferred_size) and must not blow
                # up with a confusing "不支援的領養問卷答案" dead end.
                tap_result = await conversation.handle(
                    token=token,
                    adopter_user_id=adopter_id,
                    action="answer",
                    value="companionship",
                    event_id="e-answer-motivation-stale",
                )
                assert tap_result.state == AdoptionDraftState.ANSWERING_PREFERENCE_SIZE

                refreshed = await repository.get_by_token(token)
                assert refreshed.answers["adoption_motivation"] == "companionship"
                assert "preferred_size" not in refreshed.answers
                assert (
                    refreshed.current_step
                    == AdoptionDraftState.ANSWERING_PREFERENCE_SIZE.value
                )
    finally:
        await _cleanup(organization_id=organization_id, adopter_id=adopter_id)
