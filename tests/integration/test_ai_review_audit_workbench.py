from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.ai_review import AIReviewService


class _Repository:
    def __init__(self, observation):
        self.observation = observation

    async def get(self, _observation_id):
        return self.observation


class _Audit:
    def __init__(self):
        self.records = []

    async def record(self, **payload):
        self.records.append(payload)


@pytest.mark.asyncio
async def test_ai_review_preserves_raw_output_and_records_human_decision() -> None:
    observation = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        status="succeeded",
        raw_ai_output={"label": "possible-change"},
        validated_ai_observation={"label": "possible-change"},
        human_review_result=None,
        reviewed_by=None,
        reviewed_at=None,
    )
    audit = _Audit()
    result = await AIReviewService(_Repository(observation), audit=audit).review(
        observation.id,
        actor_user_id=uuid4(),
        action="confirm",
        reason="人工確認",
    )

    assert result.raw_ai_output == {"label": "possible-change"}
    assert result.status == "confirmed"
    assert audit.records[0]["action"] == "ai_observation.reviewed"
