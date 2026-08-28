from __future__ import annotations

from pathlib import Path

import pytest
from services.api.app.infrastructure.line import messaging_api_adapter as adapter_module
from services.api.app.infrastructure.line.messaging_api_adapter import (
    LineMessagingApiAdapter,
    close_shared_line_client,
    shared_line_client,
)


@pytest.mark.asyncio
async def test_adapters_share_one_client_instead_of_leaking_one_each() -> None:
    """adapter 在 per-request DI 與 webhook handler 都會被建立；各自開 client 會漏連線池。"""
    await close_shared_line_client()
    try:
        first = LineMessagingApiAdapter()
        second = LineMessagingApiAdapter()
        assert first.client is second.client
        assert first.client is shared_line_client()
    finally:
        await close_shared_line_client()


@pytest.mark.asyncio
async def test_shared_client_is_recreated_after_close() -> None:
    await close_shared_line_client()
    first = shared_line_client()
    await close_shared_line_client()
    assert first.is_closed
    second = shared_line_client()
    try:
        assert second is not first
        assert not second.is_closed
    finally:
        await close_shared_line_client()


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    shared_line_client()
    await close_shared_line_client()
    await close_shared_line_client()
    assert adapter_module._shared_client is None


@pytest.mark.asyncio
async def test_explicit_client_is_not_replaced_by_the_shared_one() -> None:
    import httpx

    own = httpx.AsyncClient()
    try:
        assert LineMessagingApiAdapter(client=own).client is own
    finally:
        await own.aclose()
        await close_shared_line_client()


def test_app_lifespan_closes_the_shared_client() -> None:
    """沒有這個 hook，client 會活到 process 結束。"""
    source = Path("services/api/app/main.py").read_text(encoding="utf-8")
    assert "close_shared_line_client" in source
    assert "lifespan=_lifespan" in source
