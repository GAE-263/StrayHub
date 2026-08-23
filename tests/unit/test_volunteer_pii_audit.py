from datetime import datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.ports.pii import PiiCollectionAuditEvent, PiiRevealAuditEvent
from services.api.app.infrastructure.security import pii_reveal_audit
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


class _FailingCollectionSession(_Session):
    async def flush(self) -> None:
        self.events.append("flush")
        raise RuntimeError("synthetic audit database failure")

    async def rollback(self) -> None:
        self.events.append("rollback")


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


@pytest.mark.asyncio
async def test_collection_auditor_flushes_allowlisted_metadata_without_committing() -> None:
    session = _Session()
    auditor = pii_reveal_audit.TransactionalPiiCollectionAuditor(session)
    sentinel_identity = "A123456789"
    event = PiiCollectionAuditEvent(
        organization_id=uuid4(),
        application_id=uuid4(),
        actor_user_id=uuid4(),
        consent_acknowledged=True,
        purpose_code="insurance_verification",
        policy_version="organization-policy-v3",
        encryption_key_version="test-v1",
        delete_after=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )

    await auditor.persist_atomic_collection(event)

    assert session.events == ["add", "flush"]
    assert session.record.action == "insurance_identity.submitted"
    assert session.record.organization_id == event.organization_id
    assert session.record.actor_user_id == event.actor_user_id
    assert session.record.resource_id == event.application_id
    assert session.record.after_data == {
        "consent_acknowledged": True,
        "data_category": "insurance_identity",
        "purpose_code": "insurance_verification",
        "policy_version": "organization-policy-v3",
        "encryption_key_version": "test-v1",
        "delete_after": "2026-09-22T00:00:00+00:00",
    }
    assert sentinel_identity not in repr(session.record.after_data)
    assert "ciphertext" not in repr(session.record.after_data)


@pytest.mark.asyncio
async def test_collection_auditor_rolls_back_and_redacts_flush_failure() -> None:
    session = _FailingCollectionSession()
    auditor = pii_reveal_audit.TransactionalPiiCollectionAuditor(session)
    sentinel = "synthetic audit database failure"
    event = PiiCollectionAuditEvent(
        organization_id=uuid4(),
        application_id=uuid4(),
        actor_user_id=uuid4(),
        consent_acknowledged=True,
        purpose_code="insurance_verification",
        policy_version="organization-policy-v3",
        encryption_key_version="test-v1",
        delete_after=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )

    with pytest.raises(DomainError) as error:
        await auditor.persist_atomic_collection(event)

    assert session.events == ["add", "flush", "rollback"]
    assert error.value.code == "pii_audit_unavailable"
    assert error.value.status_code == 503
    assert sentinel not in str(error.value)
    assert error.value.__cause__ is None
