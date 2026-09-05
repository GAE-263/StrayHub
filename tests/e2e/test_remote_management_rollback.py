from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from scripts import rollback_remote_management as rollback
from scripts.rollback_remote_management import (
    execute_ordered_rollback,
    switch_gateway_to_line_only,
)


def test_gateway_switch_generates_line_only_then_validates_and_reloads(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], *, check: bool) -> CompletedProcess[str]:
        assert check is True
        calls.append(command)
        return CompletedProcess(command, 0)

    switch_gateway_to_line_only(
        runtime_dir=tmp_path,
        api_port=8001,
        web_port=3001,
        gateway_port=8082,
        runner=runner,
    )
    rendered = (tmp_path / "public-tunnel.nginx.conf").read_text()
    assert "location = /login" not in rendered
    assert "location = /v1/auth/login" not in rendered
    assert "location = /v1/line/webhook" in rendered
    assert calls[0][-1] == "-t"
    assert calls[1][-2:] == ["-s", "reload"]


@pytest.mark.asyncio
async def test_rollback_denies_gateway_before_revoking_sessions() -> None:
    calls: list[str] = []
    moments = iter(
        [
            datetime(2026, 9, 5, tzinfo=timezone.utc),
            datetime(2026, 9, 5, tzinfo=timezone.utc) + timedelta(seconds=4),
        ]
    )

    async def switch() -> None:
        calls.append("switch")

    async def probe_management() -> None:
        calls.append("management-denied")

    async def probe_line() -> None:
        calls.append("line-available")

    async def revoke():
        calls.append("revoke")
        return {"sessions_revoked": 3, "refresh_tokens_revoked": 4}

    evidence = await execute_ordered_rollback(
        switch_gateway=switch,
        verify_management_denied=probe_management,
        verify_line_available=probe_line,
        revoke_remote_sessions=revoke,
        now=lambda: next(moments),
    )
    assert calls == ["switch", "management-denied", "line-available", "revoke"]
    assert evidence.duration_seconds == 4
    assert evidence.reason == "remote_management_rollback"
    assert evidence.sessions_revoked == 3
    rendered = evidence.to_json().lower()
    assert "refresh_token" not in rendered
    assert "authorization" not in rendered
    assert "password" not in rendered


@pytest.mark.asyncio
async def test_failed_gateway_deny_never_revokes_sessions() -> None:
    revoked = False

    async def noop() -> None:
        return None

    async def fail() -> None:
        raise RuntimeError("management still reachable")

    async def revoke():
        nonlocal revoked
        revoked = True
        return {"sessions_revoked": 1, "refresh_tokens_revoked": 1}

    with pytest.raises(RuntimeError, match="still reachable"):
        await execute_ordered_rollback(
            switch_gateway=noop,
            verify_management_denied=fail,
            verify_line_available=noop,
            revoke_remote_sessions=revoke,
        )
    assert revoked is False


@pytest.mark.asyncio
async def test_line_server_error_never_reports_success_or_revokes_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    revoked = False

    def switch_gateway(**_kwargs: object) -> None:
        return None

    def probe(_port: int, path: str, *, method: str) -> int:
        assert method in {"GET", "POST"}
        return 404 if path != "/v1/line/webhook" else 500

    async def revoke() -> rollback.RemoteSessionRollbackResult:
        nonlocal revoked
        revoked = True
        return rollback.RemoteSessionRollbackResult(1, 1)

    monkeypatch.setattr(rollback, "switch_gateway_to_line_only", switch_gateway)
    monkeypatch.setattr(rollback, "_probe_status", probe)
    monkeypatch.setattr(rollback, "_revoke_database_sessions", revoke)

    with pytest.raises(RuntimeError, match="LINE webhook is unavailable"):
        await rollback._run(
            Namespace(
                runtime_dir=tmp_path,
                api_port=8001,
                web_port=3001,
                gateway_port=8082,
                nginx_bin="nginx",
            )
        )
    assert revoked is False


@pytest.mark.asyncio
async def test_unsigned_line_rejection_confirms_reachability_before_revocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    revoked = False

    def switch_gateway(**_kwargs: object) -> None:
        return None

    def probe(_port: int, path: str, *, method: str) -> int:
        assert method in {"GET", "POST"}
        return 401 if path == "/v1/line/webhook" else 404

    async def revoke() -> rollback.RemoteSessionRollbackResult:
        nonlocal revoked
        revoked = True
        return rollback.RemoteSessionRollbackResult(1, 2)

    monkeypatch.setattr(rollback, "switch_gateway_to_line_only", switch_gateway)
    monkeypatch.setattr(rollback, "_probe_status", probe)
    monkeypatch.setattr(rollback, "_revoke_database_sessions", revoke)

    evidence = await rollback._run(
        Namespace(
            runtime_dir=tmp_path,
            api_port=8001,
            web_port=3001,
            gateway_port=8082,
            nginx_bin="nginx",
        )
    )
    assert revoked is True
    assert evidence.line_available is True
    assert (evidence.sessions_revoked, evidence.refresh_records_revoked) == (1, 2)
