from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest
from fastapi import BackgroundTasks
from scripts.configure_runtime_role import configure
from services.api.app.api.line_webhook import (
    _growth_diary_event_transaction,
    _handle_growth_diary_message,
    _resolve_growth_diary_pending,
)
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.growth_diary import GrowthDiaryEntry
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _base_database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test",
    )


async def _seed(connection, *, line_user_id: str) -> tuple:
    organization_id, adopter_id, animal_id = uuid4(), uuid4(), uuid4()
    draft_id, inquiry_id = uuid4(), uuid4()
    await connection.execute(
        "INSERT INTO organizations (id, name, code, status, created_at, updated_at) "
        "VALUES ($1, 'Diary RLS Shelter', $2, 'active', now(), now())",
        organization_id,
        f"RLS-{organization_id.hex[:10]}",
    )
    await connection.execute(
        "INSERT INTO users (id, username, display_name, status, created_at, updated_at) "
        "VALUES ($1, $2, 'Diary RLS Adopter', 'active', now(), now())",
        adopter_id,
        f"rls-{adopter_id.hex[:10]}",
    )
    await connection.execute(
        "INSERT INTO line_user_bindings (id, line_user_id, user_id, status, created_at, "
        "updated_at) VALUES ($1, $2, $3, 'active', now(), now())",
        uuid4(),
        line_user_id,
        adopter_id,
    )
    await connection.execute(
        "INSERT INTO animals (id, organization_id, name, shelter_number, status, is_adoptable, "
        "created_at, updated_at) VALUES ($1, $2, '小福', 'C-001', 'active', false, now(), now())",
        animal_id,
        organization_id,
    )
    # RLS is FORCEd on the owner too, so seed under platform scope.
    await connection.execute("SELECT set_config('app.platform_scope', 'true', false)")
    await connection.execute(
        "INSERT INTO adoption_drafts (id, opaque_token_digest, organization_id, "
        "adopter_user_id, path, target_animal_id, current_step, answers, "
        "reconfirmation_keys, interaction_version, status, last_interaction_at, expires_at, "
        "created_at, updated_at) "
        "VALUES ($1, $2, $3, $4, 'specific_animal', $5, 'submitted', '{}'::jsonb, "
        "'[]'::jsonb, 1, 'submitted', now(), now() + interval '1 day', now(), now())",
        draft_id,
        draft_id.hex,
        organization_id,
        adopter_id,
        animal_id,
    )
    await connection.execute(
        "INSERT INTO adoption_inquiries (id, organization_id, draft_id, adopter_user_id, path, "
        "target_animal_id, animal_name_snapshot, shelter_number_snapshot, answers, "
        "adopter_name, phone_number, status, submitted_at, created_at, updated_at) "
        "VALUES ($1, $2, $3, $4, 'specific_animal', $5, '小福', 'C-001', '{}'::jsonb, "
        "'王小明', '0911222333', 'submitted', now(), now(), now())",
        inquiry_id,
        organization_id,
        draft_id,
        adopter_id,
        animal_id,
    )
    await connection.execute(
        "INSERT INTO growth_diary_drafts (adopter_user_id, organization_id, inquiry_id, "
        "animal_id, created_at, updated_at) VALUES ($1, $2, $3, $4, now(), now())",
        adopter_id,
        organization_id,
        inquiry_id,
        animal_id,
    )
    return organization_id, adopter_id


@pytest.mark.asyncio
async def test_growth_diary_text_reply_works_under_runtime_role_rls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pending-draft peek runs in authentication-user scope, but `animals`
    only has a tenant-scoped policy. Under the real non-bypass runtime role the
    save must still find the animal instead of raising
    growth_diary_source_not_found. Other diary tests set organization scope
    themselves or run as the table owner, so they cannot catch this."""
    base = urlsplit(_base_database_url())
    database = f"strayhub_diary_rls_{uuid4().hex[:12]}"
    maintenance_url = urlunsplit(("postgresql", base.netloc, "/postgres", "", ""))
    owner_url = urlunsplit(("postgresql", base.netloc, f"/{database}", "", ""))
    async_url = urlunsplit(("postgresql+asyncpg", base.netloc, f"/{database}", "", ""))
    monkeypatch.setattr(get_settings(), "celery_ai_enabled", False)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    maintenance = await asyncpg.connect(maintenance_url)
    runtime_engine = None
    line_user_id = f"Udiaryrls{uuid4().hex}"
    try:
        await maintenance.execute(f'CREATE DATABASE "{database}"')
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=dict(os.environ, DATABASE_URL=async_url),
            capture_output=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr.decode()
        await configure(async_url, apply=True)
        owner = await asyncpg.connect(owner_url)
        try:
            organization_id, adopter_id = await _seed(owner, line_user_id=line_user_id)
        finally:
            await owner.close()

        runtime_engine = create_async_engine(async_url, pool_size=1, max_overflow=0)

        @event.listens_for(runtime_engine.sync_engine, "connect")
        def use_runtime_role(connection, _record) -> None:
            connection.autocommit = True
            cursor = connection.cursor()
            cursor.execute("SET ROLE strayhub_runtime")
            cursor.close()
            connection.autocommit = False

        sessions = async_sessionmaker(runtime_engine, expire_on_commit=False)
        async with sessions() as session:
            async with _growth_diary_event_transaction(
                session, event_id="diary-rls", background_tasks=BackgroundTasks()
            ) as boundary:
                pending = await _resolve_growth_diary_pending(session, line_user_id)
                assert pending is not None
                resolved_user_id, draft = pending
                assert resolved_user_id == adopter_id
                await _handle_growth_diary_message(
                    session,
                    MockLineAdapter(),
                    {
                        "webhookEventId": "diary-rls",
                        "replyToken": "reply",
                        "source": {"userId": line_user_id},
                        "message": {"type": "text", "text": "今天胃口很好"},
                    },
                    adopter_user_id=resolved_user_id,
                    pending_draft=draft,
                    event_boundary=boundary,
                )
        async with sessions() as session, session.begin():
            await set_organization_scope(session, organization_id)
            entry = await session.scalar(
                select(GrowthDiaryEntry).where(GrowthDiaryEntry.organization_id == organization_id)
            )
            assert entry is not None
            assert entry.note == "今天胃口很好"
    finally:
        if runtime_engine is not None:
            await runtime_engine.dispose()
        await maintenance.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        await maintenance.close()
