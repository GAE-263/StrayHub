from __future__ import annotations

import httpx
import pytest
from services.api.app.api.authentication import get_session_service
from services.api.app.api.dependencies import request_session
from services.api.app.api.errors import DomainError
from services.api.app.main import app
from sqlalchemy.exc import OperationalError


class RecordingSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class RateLimitedLoginService:
    async def login(self, *, username: str, password: str, client_ip: str) -> dict:
        assert username == "synthetic-admin"
        assert password == "wrong-password"
        assert client_ip == "127.0.0.1"
        raise DomainError(
            "login_rate_limited",
            "登入暫時無法處理，請稍後再試",
            429,
            headers={"Retry-After": "900"},
        )


@pytest.mark.asyncio
async def test_login_api_commits_abuse_state_and_returns_retry_after() -> None:
    session = RecordingSession()
    service = RateLimitedLoginService()

    async def override_session() -> RecordingSession:
        return session

    async def override_service() -> RateLimitedLoginService:
        return service

    app.dependency_overrides[request_session] = override_session
    app.dependency_overrides[get_session_service] = override_service
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/auth/login",
                json={
                    "username": "synthetic-admin",
                    "password": "wrong-password",
                },
            )
    finally:
        app.dependency_overrides.pop(get_session_service, None)
        app.dependency_overrides.pop(request_session, None)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "900"
    assert response.json()["code"] == "login_rate_limited"
    assert session.commits == 1


class SuccessfulLoginService:
    def __init__(self) -> None:
        self.client_ip: str | None = None

    async def login(self, *, username: str, password: str, client_ip: str) -> dict:
        self.client_ip = client_ip
        return {"access_token": "synthetic-access-token"}


@pytest.mark.asyncio
async def test_login_api_remains_json_post_and_ignores_forwarded_for() -> None:
    session = RecordingSession()
    service = SuccessfulLoginService()

    async def override_session() -> RecordingSession:
        return session

    async def override_service() -> SuccessfulLoginService:
        return service

    app.dependency_overrides[request_session] = override_session
    app.dependency_overrides[get_session_service] = override_service
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/auth/login",
                json={"username": "staff", "password": "correct"},
                headers={"X-Forwarded-For": "203.0.113.45"},
            )
    finally:
        app.dependency_overrides.pop(get_session_service, None)
        app.dependency_overrides.pop(request_session, None)

    assert response.status_code == 200
    assert response.json() == {"access_token": "synthetic-access-token"}
    assert service.client_ip == "127.0.0.1"
    assert session.commits == 1


class UnavailableLoginService:
    async def login(self, *, username: str, password: str, client_ip: str) -> dict:
        raise OperationalError("synthetic statement", {}, Exception("database unavailable"))


@pytest.mark.asyncio
async def test_login_api_fails_closed_when_abuse_storage_is_unavailable() -> None:
    session = RecordingSession()

    async def override_session() -> RecordingSession:
        return session

    async def override_service() -> UnavailableLoginService:
        return UnavailableLoginService()

    app.dependency_overrides[request_session] = override_session
    app.dependency_overrides[get_session_service] = override_service
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/auth/login",
                json={"username": "staff", "password": "correct"},
            )
    finally:
        app.dependency_overrides.pop(get_session_service, None)
        app.dependency_overrides.pop(request_session, None)

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
    assert session.commits == 0
