import json
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.report_inbox import ProcessReportRequest, process_report
from services.api.app.application.ai_review import AIReviewService
from services.api.app.application.report_inbox_service import ReportInboxService
from services.api.app.infrastructure.ai.gemini_client import GeminiClient
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.repositories.ai_observation_repository import (
    AIObservationRepository,
)
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter
from services.worker.app.persistence.session import create_worker_session_factory
from sqlalchemy import text

from tests.integration.test_ai_worker_wiring import _cleanup, _database_url, _Fixture, _run, _seed


@pytest.fixture(autouse=True)
def summary_credentials(monkeypatch):
    # Fake credentials only select the client branch; every generation call is mocked.
    from services.worker.app.handlers import ai_job_runner

    real_settings = ai_job_runner.get_worker_settings()
    settings = SimpleNamespace(**real_settings.model_dump())
    settings.gemini_api_key = "test-key"
    settings.gemini_service_account_path = None
    monkeypatch.setattr(ai_job_runner, "get_worker_settings", lambda: settings)


@pytest.mark.asyncio
async def test_summary_worker_and_review_isolation_conflict_and_history(monkeypatch):
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=())
    connection = await asyncpg.connect(_database_url())
    factory = create_worker_session_factory()
    try:
        await connection.execute(
            "UPDATE ai_processing_jobs SET job_type='care_report_summary' WHERE id=$1",
            fixture.job_id,
        )
        calls = []

        async def generate(self, prompt):
            calls.append(prompt)
            return json.dumps(
                {
                    "attention_level": "review",
                    "summary": "原始內容待確認。",
                    "evidence": [{"field": "note", "quote": "原始內容"}],
                    "uncertainties": [],
                    "information_quality": "insufficient",
                }
            )

        monkeypatch.setattr(GeminiClient, "generate_report_summary", generate)
        assert await _run(fixture, MockAIAdapter(), storage) == 1
        assert len(calls) == 1
        row = await connection.fetchrow(
            "SELECT summary_data,summary_status,review_status,note FROM care_reports WHERE id=$1",
            fixture.report_id,
        )
        assert row["summary_status"] == "succeeded"
        assert row["review_status"] == "pending"
        assert row["note"] == "原始內容"
        assert await _run(fixture, MockAIAdapter(), storage) == 0
        async with factory() as session:
            await set_organization_scope(session, fixture.organization_id)
            service = ReportInboxService(session, fixture.organization_id)
            result = await service.process(
                fixture.report_id,
                actor_user_id=fixture.user_id,
                status="follow_up",
                note="下一班查看",
                expected_version=0,
            )
            assert result["review_version"] == 1
            await session.commit()
        async with factory() as session:
            await set_organization_scope(session, fixture.organization_id)
            service = ReportInboxService(session, fixture.organization_id)
            with pytest.raises(DomainError, match="同事已更新"):
                await service.process(
                    fixture.report_id,
                    actor_user_id=fixture.user_id,
                    status="acknowledged",
                    note="",
                    expected_version=0,
                )
            await session.rollback()
            result = await service.process(
                fixture.report_id,
                actor_user_id=fixture.user_id,
                status="resolved",
                note="已查看並告知負責人",
                expected_version=1,
            )
            assert len(result["review_history"]) == 2
            assert result["summary_status"] == "succeeded"
            await session.commit()
        async with factory() as session:
            await set_organization_scope(session, fixture.organization_id)
            repo = AIObservationRepository(session, fixture.organization_id)
            observation = (await repo.list_for_job(fixture.job_id))[0]
            reviewer = AIReviewService(repo)
            await reviewer.review(
                observation.id,
                actor_user_id=fixture.user_id,
                action="reject",
                reason="人工改看原文",
            )
            detail = await ReportInboxService(session, fixture.organization_id).detail(
                fixture.report_id
            )
            assert detail["summary_status"] == "rejected"
            assert detail["review_status"] == "resolved"
            corrected = dict(
                observation.validated_ai_observation, summary="工作人員確認原始內容待補充。"
            )
            await reviewer.review(
                observation.id,
                actor_user_id=fixture.user_id,
                action="correct",
                result=corrected,
                reason="補充語意",
            )
            await session.flush()
            detail = await ReportInboxService(session, fixture.organization_id).detail(
                fixture.report_id
            )
            assert detail["summary"]["summary"] == corrected["summary"]
            assert detail["review_status"] == "resolved"
            await session.commit()
        async with factory() as session:
            other = uuid4()
            await set_organization_scope(session, other)
            with pytest.raises(DomainError):
                await ReportInboxService(session, other).detail(fixture.report_id)
            with pytest.raises(DomainError):
                await ReportInboxService(session, other).process(
                    fixture.report_id,
                    actor_user_id=fixture.user_id,
                    status="acknowledged",
                    note="",
                    expected_version=2,
                )
            await session.rollback()
            await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
            await set_organization_scope(session, other)
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM care_reports WHERE id=:id"),
                    {"id": fixture.report_id},
                )
                == 0
            )
    finally:
        await connection.execute(
            "DELETE FROM audit_records WHERE organization_id=$1", fixture.organization_id
        )
        await connection.close()
        await factory.kw["bind"].dispose()
        await _cleanup(fixture)


@pytest.mark.asyncio
async def test_processing_rejects_volunteer_before_database_access():
    with pytest.raises(DomainError):
        await process_report(
            uuid4(),
            ProcessReportRequest(status="acknowledged", expected_version=0),
            RequestContext(
                user_id=uuid4(), organization_id=uuid4(), membership_id=uuid4(), role="VOLUNTEER"
            ),
            None,
        )


@pytest.mark.asyncio
async def test_failed_model_keeps_original_and_rules(monkeypatch):
    fixture = _Fixture()
    storage = await _seed(fixture, subjects=())
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            "UPDATE ai_processing_jobs SET job_type='care_report_summary',retry_count=2 "
            "WHERE id=$1",
            fixture.job_id,
        )

        async def generate(self, prompt):
            return '{"bad":"schema"}'

        monkeypatch.setattr(GeminiClient, "generate_report_summary", generate)
        await _run(fixture, MockAIAdapter(), storage)
        report = await connection.fetchrow(
            "SELECT summary_status,note,review_status FROM care_reports WHERE id=$1",
            fixture.report_id,
        )
        assert report["summary_status"] == "failed"
        assert report["note"] == "原始內容"
        assert report["review_status"] == "pending"
    finally:
        await connection.close()
        await _cleanup(fixture)
