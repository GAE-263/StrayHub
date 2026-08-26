from uuid import uuid4

import pytest

from tests.security.test_liff_exchange_authorization import (
    ResultService,
    TransactionProbe,
    organization,
    post_exchange,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["NEW", "PENDING", "SUSPENDED", "ACTIVE"])
async def test_http_exchange_state_matrix_enforces_active_only_credentials(state: str) -> None:
    transaction = TransactionProbe()
    result = {"state": state, "organization": organization()}
    if state == "NEW":
        result["next_path"] = "/volunteer-application"
    elif state == "ACTIVE":
        result.update(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 900,
                "session_id": uuid4(),
                "user_id": uuid4(),
                "user": {"role": "VOLUNTEER"},
                "next_path": "/animal-confirmation",
            }
        )

    response = await post_exchange(ResultService(transaction, result=result), transaction)

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == state
    credential_keys = {
        "access_token",
        "refresh_token",
        "expires_in",
        "session_id",
        "user_id",
        "user",
    }
    if state == "ACTIVE":
        assert credential_keys <= body.keys()
    else:
        assert credential_keys.isdisjoint(body)
    assert transaction.commits == 1
    assert transaction.rollbacks == 0
