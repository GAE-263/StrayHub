from __future__ import annotations

import json
import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.application.adoption_inbox_service import AdoptionInboxService
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
                for index, value in enumerate(
                    [
                        "house",
                        "experienced",
                        "has_cats",
                        "adults_only",
                        "retired",
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

                assert result.state == AdoptionDraftState.SELECTING_MATCHED_ANIMAL
                assert result.candidate_match_ids[0] == medium_high

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

                inbox = AdoptionInboxService(session, organization_id)
                detail = await inbox.detail(submit_result.inquiry_id)
                assert detail["target_animal_id"] == str(medium_high)
                assert detail["phone_number"] == "0912345678"
                assert detail["status"] == "new"

                updated = await inbox.update_status(
                    submit_result.inquiry_id,
                    status="contacted",
                    staff_notes="已致電聯絡",
                    actor_user_id=adopter_id,
                )
                assert updated["status"] == "contacted"
                assert updated["staff_notes"] == "已致電聯絡"
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
                for index, value in enumerate(
                    [
                        "house",
                        "first_time",
                        "none",
                        "adults_only",
                        "work_from_home",
                    ]
                ):
                    result = await conversation.handle(
                        token=token,
                        adopter_user_id=adopter_id,
                        action="answer",
                        value=value,
                        event_id=f"e-answer-{index}",
                    )
                assert result.state == AdoptionDraftState.AWAITING_PHONE_NUMBER

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
                inbox = AdoptionInboxService(session, organization_id)
                detail = await inbox.detail(submit_result.inquiry_id)
                assert detail["target_animal_id"] == str(target_animal_id)
                assert detail["path"] == "specific_animal"
                # No candidate pool is ranked on this path, but the target
                # animal is still scored against the collected preferences so
                # the LINE report card has something to show.
                snapshot = detail["match_scores_snapshot"]
                assert snapshot == [
                    {"animal_id": str(target_animal_id), "score": 0.0, "reasons": []}
                ]
    finally:
        await _cleanup(organization_id=organization_id, adopter_id=adopter_id)
