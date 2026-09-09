from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
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
async def test_concurrent_questionnaire_clicks_serialize_on_latest_version() -> None:
    organization_id, adopter_id, animal_id = uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    try:
        await _insert_fixtures(
            organization_id=organization_id,
            adopter_id=adopter_id,
            animal_ids=[(animal_id, "連點測試犬", "medium", "medium", [])],
        )
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                unscoped = AdoptionDraftRepository(session, None)
                draft, _ = await LineAdoptionDraftService(unscoped).create(
                    adopter_user_id=adopter_id
                )
                draft.organization_id = organization_id
                draft.path = "specific_animal"
                draft.target_animal_id = animal_id
                draft.current_step = AdoptionDraftState.ANSWERING_PARENTING_STYLE.value
                draft.answers = {
                    "housing_type": "apartment_small",
                    "dog_experience": "first_time",
                    "other_pets": "none",
                    "household_members": "adults_only",
                    "work_schedule": "work_from_home",
                }

        async def click(event_id: str):
            async with session_factory() as session:
                async with session.begin():
                    await set_organization_scope(session, organization_id)
                    return await LineAdoptionConversationService(
                        AdoptionDraftRepository(session, organization_id)
                    ).handle(
                        token=None,
                        adopter_user_id=adopter_id,
                        action="answer",
                        value="structured",
                        event_id=event_id,
                        expected_question="parenting_style",
                        expected_state=AdoptionDraftState.ANSWERING_PARENTING_STYLE.value,
                        expected_version=0,
                    )

        results = await asyncio.gather(click("rapid-1"), click("rapid-2"), return_exceptions=True)
        assert sum(not isinstance(result, Exception) for result in results) == 1
        stale = next(result for result in results if isinstance(result, Exception))
        assert isinstance(stale, DomainError)
        assert stale.code == "stale_adoption_action"

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                saved = await AdoptionDraftRepository(
                    session, organization_id
                ).get_active_for_adopter(adopter_id)
                assert saved.current_step == AdoptionDraftState.ANSWERING_PATIENCE.value
                assert saved.answers["parenting_style"] == "structured"
                assert "patience_level" not in saved.answers
                assert saved.interaction_version == 1
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
                # task itself (see line_webhook.py), not a user action.
                pending_draft = await repository.get_by_token(token)
                pending_draft.current_step = AdoptionDraftState.AWAITING_ADOPTER_NAME.value
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
