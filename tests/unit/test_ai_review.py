from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.ai_review import AIReviewService
from services.api.app.persistence.models.ai_observation import AIObservation


class FakeAIObservationRepository:
    def __init__(self):
        self.organization_id = uuid4()
        self.observation = AIObservation(
            organization_id=self.organization_id,
            job_id=uuid4(),
            source_type="note",
            status="pending",
            raw_ai_output={"observations": []},
        )
        self.observation.id = uuid4()

    async def get(self, observation_id):
        return self.observation if observation_id == self.observation.id else None


class FakeAudit:
    def __init__(self):
        self.records = []

    async def record(self, **values):
        self.records.append(values)


@pytest.mark.asyncio
async def test_human_correction_does_not_replace_raw_ai_output() -> None:
    repository = FakeAIObservationRepository()
    original = repository.observation.raw_ai_output
    result = await AIReviewService(repository).review(
        repository.observation.id,
        actor_user_id=uuid4(),
        action="correct",
        result={"code": "appearance.changed"},
    )

    assert result.status == "corrected"
    assert result.raw_ai_output == original


@pytest.mark.asyncio
async def test_human_review_requires_correction_and_records_audit() -> None:
    repository = FakeAIObservationRepository()
    audit = FakeAudit()
    service = AIReviewService(repository, audit=audit)

    with pytest.raises(DomainError, match="修正內容"):
        await service.review(
            repository.observation.id,
            actor_user_id=uuid4(),
            action="correct",
            result=None,
        )

    await service.review(
        repository.observation.id,
        actor_user_id=uuid4(),
        action="correct",
        result={"code": "feeding.less"},
    )
    assert audit.records[0]["action"] == "ai_observation.reviewed"
    assert repository.observation.raw_ai_output == {"observations": []}
