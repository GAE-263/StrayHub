from unittest.mock import AsyncMock

import httpx
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter


@pytest.mark.asyncio
async def test_line_push_uses_minimal_recipient_and_message_contract() -> None:
    response = httpx.Response(200, request=httpx.Request("POST", "https://api.line.me"))
    client = AsyncMock()
    client.post.return_value = response
    adapter = LineMessagingApiAdapter(client=client)
    await adapter.push(to_user_id="line-user", messages=[{"type": "text", "text": "已核准"}])
    payload = client.post.await_args.kwargs["json"]
    assert payload == {
        "to": "line-user",
        "messages": [{"type": "text", "text": "已核准"}],
    }


@pytest.mark.asyncio
async def test_mock_push_has_deterministic_transient_and_terminal_failures() -> None:
    transient = MockLineAdapter(push_failure_mode="transient")
    with pytest.raises(DomainError) as transient_error:
        await transient.push(to_user_id="line-user", messages=[])
    assert transient_error.value.status_code == 503

    terminal = MockLineAdapter(push_failure_mode="terminal")
    with pytest.raises(DomainError) as terminal_error:
        await terminal.push(to_user_id="line-user", messages=[])
    assert terminal_error.value.status_code == 422
