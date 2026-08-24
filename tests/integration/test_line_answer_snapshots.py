"""LINE Bot 送出的回報必須保存顯示快照，和 LIFF 路徑一致。

原本只有 LIFF／API 路徑建立 answer_snapshots，LINE Bot 路徑建構同一個
ReportSubmissionService 時省略了該參數。於是志工的主要管道成為唯一不留快照的
路徑，選項改名後歷史回報的顯示文字會跟著變。2026-08-21 實際發生過一次。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.application.line_draft_conversation import LineDraftConversationService
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)

ANSWERS = {
    "walk_completion": "walk_completion.completed",
    "activity": "activity.usual",
    "gait": "gait.normal",
    "defecation": "defecation.normal",
    "animal_interaction": "animal_interaction.friendly",
    "appearance_special_status": "appearance.none_found",
}


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


class _Fixture:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.user_id = uuid4()
        self.membership_id = uuid4()
        self.area_id = uuid4()
        self.animal_id = uuid4()
        self.draft_id = uuid4()


async def _seed(fixture: _Fixture) -> None:
    now = datetime.now(timezone.utc)
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            "INSERT INTO organizations (id, name, code, status, created_at, updated_at)"
            " VALUES ($1, 'Snapshot Shelter', $2, 'active', now(), now())",
            fixture.organization_id,
            f"SNAP-{fixture.organization_id.hex[:9]}",
        )
        await connection.execute(
            "INSERT INTO users (id, username, display_name, status, created_at, updated_at)"
            " VALUES ($1, $2, 'Snapshot Volunteer', 'active', now(), now())",
            fixture.user_id,
            f"snap-{fixture.user_id.hex[:10]}",
        )
        await connection.execute(
            "INSERT INTO organization_memberships"
            " (id, organization_id, user_id, role, status, created_at, updated_at,"
            "  valid_from, expires_at)"
            " VALUES ($1, $2, $3, 'VOLUNTEER', 'active', now(), now(),"
            "         now() - interval '1 hour', now() + interval '7 days')",
            fixture.membership_id,
            fixture.organization_id,
            fixture.user_id,
        )
        await connection.execute(
            "INSERT INTO shelter_areas"
            " (id, organization_id, name, area_type, status, created_at, updated_at)"
            " VALUES ($1, $2, 'Snapshot Cage', 'cage', 'active', now(), now())",
            fixture.area_id,
            fixture.organization_id,
        )
        await connection.execute(
            "INSERT INTO animals"
            " (id, organization_id, name, shelter_number, area_id, status,"
            "  created_at, updated_at)"
            " VALUES ($1, $2, '快照小狗', $3, $4, 'active', now(), now())",
            fixture.animal_id,
            fixture.organization_id,
            f"SNP{fixture.animal_id.hex[:11]}",
            fixture.area_id,
        )
        await connection.execute(
            "INSERT INTO daily_reportable_scopes"
            " (id, organization_id, animal_id, volunteer_user_id, starts_at, ends_at,"
            "  status, created_at, updated_at)"
            " VALUES ($1, $2, $3, $4, $5, $6, 'active', now(), now())",
            uuid4(),
            fixture.organization_id,
            fixture.animal_id,
            fixture.user_id,
            now - timedelta(days=1),
            now + timedelta(days=1),
        )
        await connection.execute(
            "INSERT INTO care_report_drafts"
            " (id, opaque_token_digest, organization_id, volunteer_user_id, membership_id,"
            "  animal_id, current_step, answers, status, last_interaction_at, expires_at,"
            "  created_at, updated_at, reconfirmation_keys, modification_summary)"
            " VALUES ($1, $2, $3, $4, $5, $6, 'reviewing', $7, 'active', now(),"
            "         now() + interval '1 day', now(), now(), $8, $9)",
            fixture.draft_id,
            f"digest-{fixture.draft_id.hex}",
            fixture.organization_id,
            fixture.user_id,
            fixture.membership_id,
            fixture.animal_id,
            json.dumps(ANSWERS),
            json.dumps([]),
            json.dumps({}),
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


async def _cleanup(fixture: _Fixture) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        for table in (
            "observation_option_usages",
            "report_idempotency_keys",
            "audit_records",
            "ai_processing_jobs",
            "care_reports",
            "care_report_drafts",
            "daily_reportable_scopes",
            "animals",
            "shelter_areas",
            "organization_memberships",
        ):
            await connection.execute(
                f"DELETE FROM {table} WHERE organization_id = $1", fixture.organization_id
            )
        await connection.execute("DELETE FROM users WHERE id = $1", fixture.user_id)
        await connection.execute(
            "DELETE FROM organizations WHERE id = $1", fixture.organization_id
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_bot_submission_stores_display_name_snapshots() -> None:
    fixture = _Fixture()
    await _seed(fixture)
    try:
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, fixture.organization_id)
                repository = CareReportDraftRepository(session, fixture.organization_id)
                result = await LineDraftConversationService(repository).handle(
                    token=None,
                    volunteer_user_id=fixture.user_id,
                    action="submit_current",
                    value=None,
                    event_id=f"snapshot-{fixture.draft_id}",
                )
                report_id = result.report_id
        assert report_id is not None

        connection = await asyncpg.connect(_database_url())
        try:
            raw = await connection.fetchval(
                "SELECT answer_snapshots FROM care_reports WHERE id = $1", report_id
            )
        finally:
            await connection.close()

        # 這個欄位存的是 JSON，未填時是 JSON null 而不是 SQL NULL——
        # 所以 `IS NULL` 查不到它，缺漏才藏了這麼久。
        assert raw not in (None, "null"), "LINE 送出的回報沒有保存顯示快照"
        snapshots = json.loads(raw)
        assert set(snapshots) == set(ANSWERS)

        gait = snapshots["gait"]
        assert gait["code"] == "gait.normal"
        assert gait["category_code"] == "gait"
        assert gait["display_name"], "顯示名稱不可為空，否則快照沒有意義"
        assert gait["source"] in {"platform_default", "organization_extension"}
    finally:
        await _cleanup(fixture)
