from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from services.api.app.persistence.repositories.timeline_repository import TimelineRepository


class _Result:
    def __init__(self, rows: list[tuple[UUID, object]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[UUID, object]]:
        return self.rows


class _Session:
    def __init__(self, rows: list[tuple[UUID, object]]) -> None:
        self.rows = rows
        self.statements: list[object] = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.rows)


def _observation(
    *,
    observation_id: UUID,
    payload: object,
    status: str = "succeeded",
    reviewed: bool = False,
) -> object:
    return SimpleNamespace(
        id=observation_id,
        created_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        raw_ai_output=payload,
        status=status,
        human_review_result={"action": "confirm"} if reviewed else None,
    )


def _valid_payload(**overrides) -> dict:
    payload = {
        "recognized": True,
        "score": 3,
        "consistency": "正常成形",
        "has_abnormalities": False,
        "abnormality_details": None,
        "assessment": "外觀正常",
        "recommendation": "持續觀察",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_empty_report_ids_do_not_query() -> None:
    session = _Session([])
    repository = TimelineRepository(session, uuid4())

    assert await repository.stool_analyses_for_reports([]) == {}
    assert session.statements == []


@pytest.mark.asyncio
async def test_query_is_tenant_scoped_target_scoped_and_deterministic() -> None:
    session = _Session([])
    organization_id = uuid4()
    report_id = uuid4()
    repository = TimelineRepository(session, organization_id)

    await repository.stool_analyses_for_reports([report_id])

    statement = session.statements[0]
    sql = str(statement)
    assert "ai_observations.organization_id" in sql
    assert "ai_processing_jobs.organization_id" in sql
    assert "ai_processing_jobs.target_type" in sql
    assert "ai_processing_jobs.target_id IN" in sql
    assert "ORDER BY ai_observations.created_at, ai_observations.id" in sql
    values = list(statement.compile().params.values())
    assert values.count(organization_id) == 2
    assert "care_report" in values
    assert [report_id] in values


@pytest.mark.asyncio
async def test_latest_valid_retry_wins_with_same_timestamp_tie() -> None:
    report_id = uuid4()
    first_id = UUID(int=1)
    malformed_id = UUID(int=2)
    latest_id = UUID(int=3)
    session = _Session(
        [
            (report_id, _observation(observation_id=first_id, payload=_valid_payload(score=2))),
            (report_id, _observation(observation_id=malformed_id, payload={"recognized": "yes"})),
            (
                report_id,
                _observation(
                    observation_id=latest_id,
                    payload=_valid_payload(score=5, has_abnormalities=True),
                    status="corrected",
                    reviewed=True,
                ),
            ),
        ]
    )

    result = await TimelineRepository(session, uuid4()).stool_analyses_for_reports([report_id])

    assert result[report_id]["score"] == 5
    assert result[report_id]["score_label"] == "正常成形"
    assert result[report_id]["has_abnormalities"] is True
    assert result[report_id]["review_status"] == "corrected"
    assert result[report_id]["human_reviewed"] is True


@pytest.mark.asyncio
async def test_malformed_or_unrelated_provider_payload_is_ignored() -> None:
    report_id = uuid4()
    malformed = [
        {"observations": []},
        {"recognized": "false", "has_abnormalities": False},
        {"recognized": False, "has_abnormalities": "false"},
        {"recognized": True, "score": 0, "has_abnormalities": False},
        {"recognized": False, "has_abnormalities": False, "assessment": 7},
    ]
    session = _Session(
        [
            (report_id, _observation(observation_id=uuid4(), payload=payload))
            for payload in malformed
        ]
    )

    assert await TimelineRepository(session, uuid4()).stool_analyses_for_reports([report_id]) == {}


@pytest.mark.asyncio
async def test_unrecognized_payload_preserves_false_and_null_values() -> None:
    report_id = uuid4()
    session = _Session(
        [
            (
                report_id,
                _observation(
                    observation_id=uuid4(),
                    payload={"recognized": False},
                ),
            )
        ]
    )

    analysis = (await TimelineRepository(session, uuid4()).stool_analyses_for_reports([report_id]))[
        report_id
    ]
    assert analysis["recognized"] is False
    assert analysis["score"] is None
    assert analysis["has_abnormalities"] is False
