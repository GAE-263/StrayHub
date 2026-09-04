import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Depends
from services.api.app.api.authentication import get_session_service
from services.api.app.api.dependencies import request_session
from services.api.app.api.errors import DomainError
from services.api.app.main import app
from services.api.app.persistence.models.identity import (
    Organization,
    RefreshTokenRecord,
    SessionRecord,
    User,
)
from services.api.app.persistence.models.volunteer_access import ShelterVolunteerEntryReference
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class FlushSessionAndRefreshThenFail:
    def __init__(
        self,
        session: AsyncSession,
        *,
        user_id,
        organization_id,
        session_id,
        refresh_id,
        fail_after_flush: bool = True,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.organization_id = organization_id
        self.session_id = session_id
        self.refresh_id = refresh_id
        self.fail_after_flush = fail_after_flush

    async def exchange_line_identity(self, **_kwargs):
        now = datetime.now(timezone.utc)
        self.session.add_all(
            [
                User(
                    id=self.user_id,
                    username=f"task6-{self.user_id.hex}",
                    display_name="Task 6 rollback user",
                    status="active",
                ),
                Organization(
                    id=self.organization_id,
                    code=f"TASK6-{self.organization_id.hex[:12]}",
                    name="Task 6 rollback organization",
                    status="active",
                ),
            ]
        )
        await self.session.flush()
        self.session.add(
            SessionRecord(
                id=self.session_id,
                user_id=self.user_id,
                active_organization_id=self.organization_id,
                status="active",
                expires_at=now + timedelta(hours=1),
            )
        )
        await self.session.flush()
        self.session.add(
            RefreshTokenRecord(
                id=self.refresh_id,
                session_id=self.session_id,
                token_digest=uuid4().hex + uuid4().hex,
                family_id=uuid4(),
                status="active",
                expires_at=now + timedelta(days=7),
            )
        )
        await self.session.flush()
        if self.fail_after_flush:
            raise DomainError("liff_exchange_unavailable", "志工入口暫時無法使用", 503)
        return {
            "state": "ACTIVE",
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 900,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user": {"role": "VOLUNTEER"},
            "organization": {
                "id": self.organization_id,
                "code": f"TASK6-{self.organization_id.hex[:12]}",
                "name": "Task 6 rollback organization",
            },
            "next_path": "/animal-confirmation",
        }


class CommitFailureSession:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.rollback_calls = 0

    def add_all(self, values) -> None:
        self.session.add_all(values)

    def add(self, value) -> None:
        self.session.add(value)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        raise RuntimeError("commit connection details")

    async def rollback(self) -> None:
        self.rollback_calls += 1
        await self.session.rollback()


def async_database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


def test_entry_reference_lifecycle_contract_is_90_days_and_revocable() -> None:
    table = ShelterVolunteerEntryReference.__table__

    assert str(table.c.expires_at.server_default.arg) == "now() + interval '90 days'"
    assert table.c.status.default.arg == "active"
    assert table.c.revoked_at.nullable is True
    assert table.c.rotation_group_id.nullable is False


@pytest.mark.asyncio
async def test_http_failure_after_session_and_refresh_flush_rolls_back_all_rows() -> None:
    engine = create_async_engine(async_database_url())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    organization_id = uuid4()
    session_id = uuid4()
    refresh_id = uuid4()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def override_service(
        session: AsyncSession = Depends(request_session),  # noqa: B008
    ) -> FlushSessionAndRefreshThenFail:
        return FlushSessionAndRefreshThenFail(
            session,
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
            refresh_id=refresh_id,
        )

    app.dependency_overrides[request_session] = override_session
    app.dependency_overrides[get_session_service] = override_service
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/auth/liff/exchange",
                json={
                    "id_token": "line-token",
                    "shelter_entry_reference": "opaque-entry-reference-0123456789abcdef",
                },
                headers={"X-Request-ID": "task6-flush-failure"},
            )

        assert response.status_code == 503
        body = response.json()
        assert body["code"] == "liff_exchange_unavailable"
        assert body["message"] == "志工入口暫時無法使用"
        assert body["request_id"] != "task6-flush-failure"
        UUID(body["request_id"])
        async with session_factory() as verification_session:
            for model, record_id in (
                (RefreshTokenRecord, refresh_id),
                (SessionRecord, session_id),
                (User, user_id),
                (Organization, organization_id),
            ):
                count = await verification_session.scalar(
                    select(func.count()).select_from(model).where(model.id == record_id)
                )
                assert count == 0
    finally:
        app.dependency_overrides.pop(get_session_service, None)
        app.dependency_overrides.pop(request_session, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_commit_failure_rolls_back_flushed_session_and_refresh_rows() -> None:
    engine = create_async_engine(async_database_url())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    organization_id = uuid4()
    session_id = uuid4()
    refresh_id = uuid4()
    commit_failure_session = None

    async def override_session() -> AsyncIterator[CommitFailureSession]:
        nonlocal commit_failure_session
        async with session_factory() as session:
            commit_failure_session = CommitFailureSession(session)
            yield commit_failure_session

    async def override_service(
        session: CommitFailureSession = Depends(request_session),  # noqa: B008
    ) -> FlushSessionAndRefreshThenFail:
        return FlushSessionAndRefreshThenFail(
            session,  # type: ignore[arg-type]
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
            refresh_id=refresh_id,
            fail_after_flush=False,
        )

    app.dependency_overrides[request_session] = override_session
    app.dependency_overrides[get_session_service] = override_service
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/auth/liff/exchange",
                json={
                    "id_token": "line-token",
                    "shelter_entry_reference": "opaque-entry-reference-0123456789abcdef",
                },
                headers={"X-Request-ID": "task6-real-commit-failure"},
            )

        assert response.status_code == 503
        body = response.json()
        assert body["code"] == "liff_exchange_unavailable"
        assert body["message"] == "志工入口暫時無法使用"
        assert body["request_id"] != "task6-real-commit-failure"
        UUID(body["request_id"])
        assert commit_failure_session is not None
        assert commit_failure_session.rollback_calls == 1
        async with session_factory() as verification_session:
            for model, record_id in (
                (RefreshTokenRecord, refresh_id),
                (SessionRecord, session_id),
                (User, user_id),
                (Organization, organization_id),
            ):
                count = await verification_session.scalar(
                    select(func.count()).select_from(model).where(model.id == record_id)
                )
                assert count == 0
    finally:
        app.dependency_overrides.pop(get_session_service, None)
        app.dependency_overrides.pop(request_session, None)
        await engine.dispose()
