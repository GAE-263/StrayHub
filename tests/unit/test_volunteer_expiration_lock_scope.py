from datetime import datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from sqlalchemy.dialects import postgresql


class EmptyScalarResult:
    def scalars(self):
        return []


class CaptureSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return EmptyScalarResult()


@pytest.mark.asyncio
async def test_expiration_candidates_lock_only_grant_rows() -> None:
    session = CaptureSession()
    repository = VolunteerAccessRepository(session, uuid4())  # type: ignore[arg-type]

    await repository.due_or_invalid_grants(now=datetime.now(timezone.utc))

    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF volunteer_access_grants SKIP LOCKED" in sql
    assert "FOR UPDATE OF users" not in sql
    assert "FOR UPDATE OF organizations" not in sql
