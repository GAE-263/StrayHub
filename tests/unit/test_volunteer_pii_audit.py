from datetime import datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.application.ports.pii import PiiRevealAuditEvent
from services.api.app.infrastructure.security.pii_reveal_audit import CommittedPiiRevealAuditor


class _Session:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.record = None

    async def execute(self, statement, parameters=None):
        self.events.append("scope")

    def add(self, record) -> None:
        self.events.append("add")
        self.record = record

    async def flush(self) -> None:
        self.events.append("flush")

    async def commit(self) -> None:
        self.events.append("commit")


class _SessionContext:
    def __init__(self, session: _Session) -> None:
        self.session = session

    async def __aenter__(self) -> _Session:
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


@pytest.mark.asyncio
async def test_committed_reveal_auditor_commits_only_allowlisted_metadata() -> None:
    session = _Session()
    auditor = CommittedPiiRevealAuditor(lambda: _SessionContext(session))
    sentinel_name = "測試志工丙"
    sentinel_phone = "0900000003"
    request_id = uuid4()
    event = PiiRevealAuditEvent(
        organization_id=uuid4(),
        application_id=uuid4(),
        actor_user_id=uuid4(),
        actor_role="SHELTER_ADMIN",
        purpose_code="application_review",
        request_id=request_id,
        policy_version="volunteer-pii-v1",
        provided_fields=("applicant_name", "phone_number"),
        encryption_key_version="test-v1",
        retention_expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )

    await auditor.persist_committed_reveal(event)

    assert session.events == ["scope"] * 5 + ["add", "flush", "commit"]
    assert session.record.action == "pii.revealed"
    assert session.record.organization_id == event.organization_id
    assert session.record.resource_id == event.application_id
    assert session.record.after_data == {
        "provided_fields": ["applicant_name", "phone_number"],
        "actor_role": "SHELTER_ADMIN",
        "data_category": ["applicant_name", "phone_number"],
        "purpose_code": "application_review",
        "request_id": str(request_id),
        "policy_version": "volunteer-pii-v1",
        "encryption_key_version": "test-v1",
        "retention_expires_at": "2027-01-01T00:00:00+00:00",
    }
    serialized_record = repr(session.record.after_data)
    assert sentinel_name not in serialized_record
    assert sentinel_phone not in serialized_record
    assert "ciphertext" not in serialized_record
