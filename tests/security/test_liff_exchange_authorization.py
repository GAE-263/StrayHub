from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from services.api.app.api.authentication import get_session_service
from services.api.app.api.dependencies import request_session
from services.api.app.api.errors import DomainError
from services.api.app.main import app

ENTRY = "opaque-entry-reference-0123456789abcdef"


class TransactionProbe:
    def __init__(self, *, fail_commit: bool = False, fail_rollback_once: bool = False) -> None:
        self.pending_rows = 0
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = fail_commit
        self.fail_rollback_once = fail_rollback_once

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("database connection details")
        self.commits += 1
        self.pending_rows = 0

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self.fail_rollback_once:
            self.fail_rollback_once = False
            raise RuntimeError("rollback connection details")
        self.pending_rows = 0


class ResultService:
    def __init__(
        self,
        transaction: TransactionProbe,
        result=None,
        error: DomainError | None = None,
    ):
        self.transaction = transaction
        self.result = result
        self.error = error

    async def exchange_line_identity(self, **_kwargs):
        if self.error is not None:
            self.transaction.pending_rows = 2
            raise self.error
        self.transaction.pending_rows = 2
        return self.result


def organization() -> dict:
    return {"id": uuid4(), "code": "ORG-A", "name": "收容所 A"}


async def post_exchange(service: ResultService, transaction: TransactionProbe) -> httpx.Response:
    async def override_service():
        return service

    async def override_session() -> AsyncIterator[TransactionProbe]:
        try:
            yield transaction
        finally:
            if transaction.pending_rows:
                await transaction.rollback()

    app.dependency_overrides[get_session_service] = override_service
    app.dependency_overrides[request_session] = override_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            return await client.post(
                "/v1/auth/liff/exchange",
                json={"id_token": "line-id-token", "shelter_entry_reference": ENTRY},
                headers={"X-Request-ID": "task6-request"},
            )
    finally:
        app.dependency_overrides.pop(get_session_service, None)
        app.dependency_overrides.pop(request_session, None)


@pytest.mark.asyncio
async def test_invalid_service_response_rolls_back_before_http_failure() -> None:
    transaction = TransactionProbe()
    service = ResultService(
        transaction,
        result={
            "state": "ACTIVE",
            "organization": organization(),
            "next_path": "/animal-confirmation",
            "user": {"role": "VOLUNTEER"},
        },
    )

    response = await post_exchange(service, transaction)

    assert response.status_code == 503
    assert response.json() == {
        "code": "liff_exchange_unavailable",
        "message": "志工入口暫時無法使用",
        "request_id": "task6-request",
    }
    assert transaction.commits == 0
    assert transaction.rollbacks == 1
    assert transaction.pending_rows == 0


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_returns_safe_dependency_error() -> None:
    transaction = TransactionProbe(fail_commit=True)
    service = ResultService(
        transaction,
        result={
            "state": "NEW",
            "organization": organization(),
            "next_path": "/volunteer-application",
        },
    )

    response = await post_exchange(service, transaction)

    assert response.status_code == 503
    assert response.json() == {
        "code": "liff_exchange_unavailable",
        "message": "志工入口暫時無法使用",
        "request_id": "task6-request",
    }
    assert transaction.commits == 0
    assert transaction.rollbacks >= 1
    assert transaction.pending_rows == 0


@pytest.mark.asyncio
async def test_rollback_failure_cannot_mask_safe_dependency_error() -> None:
    transaction = TransactionProbe(fail_commit=True, fail_rollback_once=True)
    service = ResultService(
        transaction,
        result={
            "state": "NEW",
            "organization": organization(),
            "next_path": "/volunteer-application",
        },
    )

    response = await post_exchange(service, transaction)

    assert response.status_code == 503
    assert response.json() == {
        "code": "liff_exchange_unavailable",
        "message": "志工入口暫時無法使用",
        "request_id": "task6-request",
    }
    assert transaction.rollbacks == 2
    assert transaction.pending_rows == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (
            DomainError("invalid_line_id_token", "無法確認 LINE 身分", 401),
            401,
            "invalid_line_id_token",
            "無法確認 LINE 身分",
        ),
        (
            DomainError("entry_unavailable", "此志工入口目前無法使用", 403),
            403,
            "entry_unavailable",
            "此志工入口目前無法使用",
        ),
        (
            DomainError("liff_exchange_unavailable", "志工入口暫時無法使用", 503),
            503,
            "liff_exchange_unavailable",
            "志工入口暫時無法使用",
        ),
    ],
)
async def test_http_errors_are_safe_and_leave_no_partial_state(
    error: DomainError, status_code: int, code: str, message: str
) -> None:
    transaction = TransactionProbe()

    response = await post_exchange(ResultService(transaction, error=error), transaction)

    assert response.status_code == status_code
    assert response.json() == {
        "code": code,
        "message": message,
        "request_id": "task6-request",
    }
    assert transaction.commits == 0
    assert transaction.rollbacks == 1
    assert transaction.pending_rows == 0
