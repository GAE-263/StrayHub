#!/usr/bin/env python3
"""Disable shared management routes, verify LINE, then revoke remote sessions."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.generate_public_tunnel_config import generate_runtime_configs
except ModuleNotFoundError:  # Direct executable invocation puts scripts/ on sys.path.
    from generate_public_tunnel_config import generate_runtime_configs  # type: ignore[no-redef]
from services.api.app.application.authentication.session_service import (  # noqa: E402
    REMOTE_MANAGEMENT_ROLLBACK_REASON,
    RemoteSessionRollbackResult,
    RemoteSessionRollbackService,
)
from services.api.app.config.settings import get_settings  # noqa: E402
from services.api.app.persistence.repositories.authentication_repository import (  # noqa: E402
    AuthenticationRepository,
)
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

MAX_ROLLBACK_SECONDS = 300
EXPECTED_UNSIGNED_LINE_WEBHOOK_STATUS = 401


@dataclass(frozen=True)
class RollbackEvidence:
    started_at: str
    completed_at: str
    duration_seconds: float
    reason: str
    gateway_profile: str
    management_denied: bool
    line_available: bool
    sessions_revoked: int
    refresh_records_revoked: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def switch_gateway_to_line_only(
    *,
    runtime_dir: Path,
    api_port: int,
    web_port: int,
    gateway_port: int,
    nginx_bin: str = "nginx",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    runtime_dir = runtime_dir.resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "logs").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="strayhub-rollback-") as directory:
        generated = generate_runtime_configs(
            profile_name="line-only",
            output_dir=Path(directory),
            api_port=api_port,
            web_port=web_port,
            gateway_port=gateway_port,
        )
        runner(
            [
                nginx_bin,
                "-p",
                f"{runtime_dir}/",
                "-c",
                str(generated.nginx_path),
                "-t",
            ],
            check=True,
        )
        final_nginx = runtime_dir / "public-tunnel.nginx.conf"
        final_policy = runtime_dir / "public-tunnel.traffic-policy.yaml"
        os.replace(generated.nginx_path, final_nginx)
        os.replace(generated.traffic_policy_path, final_policy)
        runner(
            [
                nginx_bin,
                "-p",
                f"{runtime_dir}/",
                "-c",
                str(final_nginx),
                "-s",
                "reload",
            ],
            check=True,
        )


async def execute_ordered_rollback(
    *,
    switch_gateway: Callable[[], Awaitable[None]],
    verify_management_denied: Callable[[], Awaitable[None]],
    verify_line_available: Callable[[], Awaitable[None]],
    revoke_remote_sessions: Callable[[], Awaitable[RemoteSessionRollbackResult | dict[str, int]]],
    now: Callable[[], datetime] | None = None,
) -> RollbackEvidence:
    clock = now or (lambda: datetime.now(timezone.utc))
    started = clock()
    await switch_gateway()
    await verify_management_denied()
    await verify_line_available()
    result = await revoke_remote_sessions()
    completed = clock()
    elapsed = (completed - started).total_seconds()
    if elapsed > MAX_ROLLBACK_SECONDS:
        raise RuntimeError("rollback exceeded the five-minute recovery objective")
    if isinstance(result, dict):
        sessions_revoked = result["sessions_revoked"]
        refresh_tokens_revoked = result["refresh_tokens_revoked"]
    else:
        sessions_revoked = result.sessions_revoked
        refresh_tokens_revoked = result.refresh_tokens_revoked
    return RollbackEvidence(
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        duration_seconds=elapsed,
        reason=REMOTE_MANAGEMENT_ROLLBACK_REASON,
        gateway_profile="line-only",
        management_denied=True,
        line_available=True,
        sessions_revoked=sessions_revoked,
        refresh_records_revoked=refresh_tokens_revoked,
    )


def _probe_status(port: int, path: str, *, method: str) -> int:
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        method=method,
        headers={"Host": "localhost"},
        data=b"" if method == "POST" else None,
    )
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - fixed loopback target
            return response.status
    except HTTPError as exc:
        return exc.code
    except URLError as exc:
        raise RuntimeError("local rollback gateway is unavailable") from exc


async def _revoke_database_sessions() -> RemoteSessionRollbackResult:
    settings = get_settings()
    database_url = settings.database_migration_url or settings.database_url
    engine = create_async_engine(database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session, session.begin():
            return await RemoteSessionRollbackService(
                AuthenticationRepository(session)
            ).revoke_remote_management_sessions()
    finally:
        await engine.dispose()


async def _run(args: argparse.Namespace) -> RollbackEvidence:
    runtime_dir = args.runtime_dir.resolve()

    async def switch_gateway() -> None:
        switch_gateway_to_line_only(
            runtime_dir=runtime_dir,
            api_port=args.api_port,
            web_port=args.web_port,
            gateway_port=args.gateway_port,
            nginx_bin=args.nginx_bin,
        )

    async def verify_management_denied() -> None:
        statuses = (
            _probe_status(args.gateway_port, "/login", method="GET"),
            _probe_status(args.gateway_port, "/v1/auth/login", method="POST"),
        )
        if statuses != (404, 404):
            raise RuntimeError("management routes remain reachable after gateway rollback")

    async def verify_line_available() -> None:
        status = _probe_status(args.gateway_port, "/v1/line/webhook", method="POST")
        if status != EXPECTED_UNSIGNED_LINE_WEBHOOK_STATUS:
            raise RuntimeError("LINE webhook is unavailable after gateway rollback")

    return await execute_ordered_rollback(
        switch_gateway=switch_gateway,
        verify_management_denied=verify_management_denied,
        verify_line_available=verify_line_available,
        revoke_remote_sessions=_revoke_database_sessions,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--api-port", type=int, default=8001)
    parser.add_argument("--web-port", type=int, default=3001)
    parser.add_argument("--gateway-port", type=int, default=8082)
    parser.add_argument("--nginx-bin", default="nginx")
    args = parser.parse_args(argv)
    try:
        evidence = asyncio.run(_run(args))
    except (OSError, RuntimeError, SQLAlchemyError, subprocess.CalledProcessError):
        parser.exit(1, "rollback failed; inspect redacted local service logs\n")
    print(evidence.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
