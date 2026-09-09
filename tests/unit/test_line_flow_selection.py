from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from services.api.app.api import line_webhook as bot
from services.api.app.api.errors import DomainError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flows", [[], ["adoption"], ["care_report"], ["growth_diary"], ["adoption", "care_report"]]
)
async def test_legacy_flow_resolves_only_unambiguous_draft(monkeypatch, flows):
    binding = SimpleNamespace(user_id=uuid4(), current_flow=None)
    session = SimpleNamespace(flush=AsyncMock())
    monkeypatch.setattr(bot.LineWebhookRepository, "binding", AsyncMock(return_value=binding))
    draft = SimpleNamespace(expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    monkeypatch.setattr(
        bot,
        "_active_adoption_draft",
        AsyncMock(return_value=draft if "adoption" in flows else None),
    )
    monkeypatch.setattr(
        bot,
        "_resolve_growth_diary_pending",
        AsyncMock(return_value=(binding.user_id, draft) if "growth_diary" in flows else None),
    )
    monkeypatch.setattr(
        bot,
        "_resolve_context",
        AsyncMock(return_value=(binding.user_id, uuid4(), uuid4(), "VOLUNTEER")),
    )
    monkeypatch.setattr(
        bot.CareReportDraftRepository,
        "get_active_for_volunteer",
        AsyncMock(return_value=draft if "care_report" in flows else None),
    )
    event = {"type": "message", "message": {"type": "text", "text": "心得"}}
    if len(flows) > 1:
        with pytest.raises(DomainError, match="多份"):
            await bot._select_line_flow(session, "test", event)
        assert binding.current_flow is None
    else:
        assert await bot._select_line_flow(session, "test", event) == next(iter(flows), None)


@pytest.mark.asyncio
async def test_unauthorized_volunteer_entry_keeps_selected_flow(monkeypatch):
    binding = SimpleNamespace(user_id=uuid4(), current_flow="adoption")
    monkeypatch.setattr(bot.LineWebhookRepository, "binding", AsyncMock(return_value=binding))
    monkeypatch.setattr(
        bot,
        "_resolve_context",
        AsyncMock(side_effect=DomainError("denied", "請先取得志工資格", 403)),
    )
    with pytest.raises(DomainError):
        await bot._select_line_flow(
            SimpleNamespace(flush=AsyncMock()),
            "test",
            {"type": "postback", "postback": {"data": "action=start_care_report"}},
        )
    assert binding.current_flow == "adoption"
