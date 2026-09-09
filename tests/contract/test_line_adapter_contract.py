import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.config.settings import Settings
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
async def test_line_push_sends_retry_key_and_accepts_duplicate_response() -> None:
    response = httpx.Response(409, request=httpx.Request("POST", "https://api.line.me"))
    client = AsyncMock()
    client.post.return_value = response
    adapter = LineMessagingApiAdapter(client=client)

    await adapter.push(
        to_user_id="line-user",
        messages=[{"type": "text", "text": "分析完成"}],
        retry_key="5d0fa3fb-50a8-4bca-8ba8-76488b6b05cd",
    )

    assert client.post.await_args.kwargs["headers"]["X-Line-Retry-Key"] == (
        "5d0fa3fb-50a8-4bca-8ba8-76488b6b05cd"
    )


@pytest.mark.asyncio
async def test_acceptance_line_push_is_fail_closed_to_hashed_allowlist() -> None:
    allowed_user = "controlled-line-user"
    allowed_digest = hashlib.sha256(allowed_user.encode()).hexdigest()
    settings = Settings(
        _env_file=None,
        app_env="acceptance",
        line_notification_recipient_allowlist_sha256=allowed_digest,
    )
    response = httpx.Response(200, request=httpx.Request("POST", "https://api.line.me"))
    client = AsyncMock()
    client.post.return_value = response
    adapter = LineMessagingApiAdapter(client=client, settings=settings)

    with pytest.raises(DomainError) as caught:
        await adapter.push(to_user_id="real-user", messages=[])
    assert caught.value.code == "line_recipient_not_allowlisted"
    client.post.assert_not_awaited()

    await adapter.push(to_user_id=allowed_user, messages=[])
    client.post.assert_awaited_once()

    with pytest.raises(DomainError):
        adapter.ensure_recipient_allowed("uncontrolled-inbound-user")


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
