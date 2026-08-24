from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import asyncpg
import pytest
from PIL import Image
from services.api.app.application.animal_selection import (
    AnimalSelectionService,
    issue_animal_confirmation_token,
)
from services.api.app.application.create_report_draft import CreateReportDraftService
from services.api.app.application.line_draft_conversation import LineDraftConversationService
from services.api.app.application.line_image_service import LineImageService
from services.api.app.application.ports.line_messaging import LineImageContent
from services.api.app.application.report_job_dispatch import ReportJobDispatchService
from services.api.app.application.timeline_service import TimelineService
from services.api.app.domain.line_care_report_state import DraftState
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
from services.api.app.persistence.repositories.reportable_scope_repository import (
    ReportableScopeRepository,
)
from services.api.app.persistence.repositories.timeline_repository import TimelineRepository


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


@pytest.mark.asyncio
async def test_local_vertical_flow_reaches_report_and_timeline_without_ai_worker() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_id, user_id, membership_id = uuid4(), uuid4(), uuid4()
    session_id, area_id, animal_id, qr_id = uuid4(), uuid4(), uuid4(), uuid4()
    raw_qr_token = f"local-flow-{qr_id}"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    report_id = None
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Local MVP Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"LOCAL-{organization_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Local MVP Volunteer', 'active', now(), now())
            """,
            user_id,
            f"local-flow-{user_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, created_at, updated_at,
                 valid_from, expires_at)
            VALUES ($1, $2, $3, 'VOLUNTEER', 'active', now(), now(),
                    now() - interval '1 hour', now() + interval '7 days')
            """,
            membership_id,
            organization_id,
            user_id,
        )
        await connection.execute(
            """
            INSERT INTO session_records
                (id, user_id, active_organization_id, status, expires_at, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', $4, now(), now())
            """,
            session_id,
            user_id,
            organization_id,
            now + timedelta(days=1),
        )
        await connection.execute(
            """
            INSERT INTO shelter_areas
                (id, organization_id, name, area_type, status, created_at, updated_at)
            VALUES ($1, $2, 'Local Cage', 'cage', 'active', now(), now())
            """,
            area_id,
            organization_id,
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, area_id, status, created_at, updated_at)
            VALUES ($1, $2, '小黑', 'VAAAG114080610', $3, 'active', now(), now())
            """,
            animal_id,
            organization_id,
            area_id,
        )
        await connection.execute(
            """
            INSERT INTO animal_qr_codes
                (id, organization_id, animal_id, token_digest, status, revoked,
                 created_at, updated_at)
                VALUES ($1, $2, $3, $4, 'active', false, now(), now())
            """,
            qr_id,
            organization_id,
            animal_id,
            hashlib.sha256(raw_qr_token.encode()).hexdigest(),
        )
        await connection.execute(
            """
            INSERT INTO daily_reportable_scopes
                (id, organization_id, animal_id, volunteer_user_id, starts_at, ends_at,
                 status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'active', now(), now())
            """,
            uuid4(),
            organization_id,
            animal_id,
            user_id,
            now - timedelta(days=1),
            now + timedelta(days=1),
        )
        await connection.execute("COMMIT")

        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                selection = AnimalSelectionService(
                    AnimalRepository(session, organization_id),
                    QrCodeRepository(session, organization_id),
                    ReportableScopeRepository(session, organization_id),
                )
                candidate = await selection.resolve_qr(
                    raw_token=raw_qr_token, user_id=user_id, role="VOLUNTEER"
                )
                assert candidate.animal.id == animal_id
                confirmed = await selection.confirm(
                    animal_id=animal_id, user_id=user_id, role="VOLUNTEER"
                )
                assert confirmed.animal.shelter_number == "VAAAG114080610"
                confirmation_token = issue_animal_confirmation_token(
                    user_id=user_id,
                    organization_id=organization_id,
                    membership_id=membership_id,
                    session_id=session_id,
                    animal_id=animal_id,
                )
                assert confirmation_token

                drafts = CareReportDraftRepository(session, organization_id)
                draft, raw_draft_token = await CreateReportDraftService(drafts).create(
                    volunteer_user_id=user_id,
                    organization_id=organization_id,
                    membership_id=membership_id,
                    session_id=session_id,
                    animal_id=animal_id,
                    confirmation_token=confirmation_token,
                )
                conversation = LineDraftConversationService(drafts)
                await conversation.handle(
                    token=raw_draft_token,
                    volunteer_user_id=user_id,
                    action="confirm_animal",
                    value=None,
                    event_id="local-confirm",
                )
                line = MockLineAdapter()

                first_answers = (
                    "walk_completion.completed",
                    "activity.usual",
                    "gait.normal",
                )
                for index, value in enumerate(first_answers):
                    result = await conversation.handle(
                        token=raw_draft_token,
                        volunteer_user_id=user_id,
                        action="answer",
                        value=value,
                        event_id=f"local-answer-{index}",
                    )
                assert result.state == DraftState.ANSWERING_DEFECATION

                result = await conversation.handle(
                    token=raw_draft_token,
                    volunteer_user_id=user_id,
                    action="answer",
                    value="defecation.soft",
                    event_id="local-answer-defecation",
                )
                assert result.state == DraftState.AWAITING_STOOL_MEDIA

                stool_image = BytesIO()
                Image.new("RGB", (3, 3), "brown").save(stool_image, format="JPEG")
                line.images["local-stool-image"] = LineImageContent(
                    "local-stool-image", stool_image.getvalue(), "image/jpeg"
                )
                await LineImageService(line, InMemoryStorageFake()).attach_to_draft(
                    message_id="local-stool-image",
                    organization_id=organization_id,
                    object_key=f"drafts/{draft.id}/local-stool.jpg",
                    draft_id=draft.id,
                    source_event_id="local-stool-image-event",
                    subject="stool",
                    session=session,
                )
                draft.current_step = DraftState.ANSWERING_ANIMAL_INTERACTION.value
                await session.flush()

                remaining_answers = (
                    "animal_interaction.friendly",
                    "appearance.none_found",
                )
                for index, value in enumerate(remaining_answers):
                    result = await conversation.handle(
                        token=raw_draft_token,
                        volunteer_user_id=user_id,
                        action="answer",
                        value=value,
                        event_id=f"local-answer-remaining-{index}",
                    )
                assert result.state == DraftState.AWAITING_MEDIA

                image = BytesIO()
                Image.new("RGB", (3, 3), "purple").save(image, format="JPEG")
                line.images["local-image"] = LineImageContent(
                    "local-image", image.getvalue(), "image/jpeg"
                )
                await LineImageService(line, InMemoryStorageFake()).attach_to_draft(
                    message_id="local-image",
                    organization_id=organization_id,
                    object_key=f"drafts/{draft.id}/local.jpg",
                    draft_id=draft.id,
                    source_event_id="local-image-event",
                    subject="portrait",
                    session=session,
                )
                draft.current_step = DraftState.AWAITING_NOTE.value
                await session.flush()
                await conversation.handle(
                    token=raw_draft_token,
                    volunteer_user_id=user_id,
                    action="skip_note",
                    value=None,
                    event_id="local-skip-note",
                )
                await conversation.handle(
                    token=raw_draft_token,
                    volunteer_user_id=user_id,
                    action="story",
                    value="今天在草地上追蝴蝶追了好久",
                    event_id="local-story",
                )
                submission = await conversation.handle(
                    token=raw_draft_token,
                    volunteer_user_id=user_id,
                    action="submit",
                    value=None,
                    event_id="local-submit",
                )
                report_id = submission.report_id
                assert report_id is not None

        assert await ReportJobDispatchService(session_factory).dispatch(
            organization_id=organization_id, report_id=report_id
        )
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, organization_id)
                days = await TimelineService(TimelineRepository(session, organization_id)).recent(
                    animal_id=animal_id, end_date=now.date()
                )
                assert len(days) == 14
                assert sum(day.report_count for day in days) == 1
    finally:
        cleanup = await asyncpg.connect(_database_url())
        try:
            await cleanup.execute("BEGIN")
            await cleanup.execute(
                "DELETE FROM care_report_media WHERE report_id IN "
                "(SELECT id FROM care_reports WHERE organization_id = $1)",
                organization_id,
            )
            await cleanup.execute(
                "DELETE FROM draft_media_assets WHERE draft_id IN "
                "(SELECT id FROM care_report_drafts WHERE organization_id = $1)",
                organization_id,
            )
            for table in (
                "report_idempotency_keys",
                "care_report_corrections",
                "ai_processing_jobs",
                "audit_records",
                # 選項使用索引以 care_report_id 為外鍵，必須先於 care_reports 刪除。
                "observation_option_usages",
                "care_reports",
                "care_report_drafts",
                "media_assets",
                "daily_reportable_scopes",
                "animal_qr_codes",
                "animals",
                "shelter_areas",
                "session_records",
                "organization_memberships",
            ):
                await cleanup.execute(
                    f"DELETE FROM {table} WHERE organization_id = $1"
                    if table != "session_records"
                    else f"DELETE FROM {table} WHERE active_organization_id = $1",
                    organization_id,
                )
            await cleanup.execute("DELETE FROM users WHERE id = $1", user_id)
            await cleanup.execute("DELETE FROM organizations WHERE id = $1", organization_id)
            await cleanup.execute("COMMIT")
        finally:
            await cleanup.close()
