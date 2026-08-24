from datetime import datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.persistence.models.volunteer_access import VolunteerApplicationProfile
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from sqlalchemy.dialects import postgresql


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _CaptureSession:
    def __init__(self, value: object) -> None:
        self.value = value
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _ScalarResult(self.value)


@pytest.mark.asyncio
async def test_application_profile_read_is_tenant_scoped_and_lockable() -> None:
    organization_id = uuid4()
    application_id = uuid4()
    profile = VolunteerApplicationProfile(
        organization_id=organization_id,
        application_id=application_id,
        applicant_name_ciphertext=b"cipher-name",
        phone_ciphertext=b"cipher-phone",
        pii_schema_version="v1",
        encryption_algorithm="AES-256-GCM",
        encryption_key_version="test-v1",
        retention_expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    session = _CaptureSession(profile)
    repository = VolunteerAccessRepository(session, organization_id)  # type: ignore[arg-type]

    result = await repository.application_profile(application_id, for_update=True)

    assert result is profile
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "volunteer_application_profiles.organization_id" in sql
    assert "volunteer_application_profiles.application_id" in sql
    assert "FOR UPDATE" in sql
