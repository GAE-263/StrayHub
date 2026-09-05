"""Persistent local development launcher; public LINE uses the existing allowlist."""

from __future__ import annotations

import argparse
import asyncio
import base64
import fcntl
import getpass
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values
from scripts.demo_credentials import require_demo_password
from scripts.local_demo import DEMO_SHELTERS, require_local_demo
from services.api.app.config.settings import Settings
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".env.dev-state.json"
KEYS = ROOT / ".env.dev-keys.json"
ACCOUNTS = (
    "demo-furkids-admin",
    "demo-platform-admin",
    "demo-furkids-volunteer",
    "demo-xindian-volunteer",
    "demo-wugu-volunteer",
)
COMPOSE = ["docker", "compose", "-f", "infra/local/docker-compose.yml"]


def configuration() -> dict[str, str]:
    env = {key: value for key, value in dotenv_values(ROOT / ".env").items() if value is not None}
    env.update(os.environ)
    env.setdefault("API_PORT", "8001")
    env.setdefault("WEB_PORT", "3001")
    env.setdefault("NGINX_PORT", "8082")
    env["API_HOST"] = env["WEB_HOST"] = "127.0.0.1"
    env["API_BASE_URL"] = f"http://127.0.0.1:{env['API_PORT']}"
    # A local login must not inherit shared-management proxy metadata.
    env["LOGIN_TRUSTED_PROXY_ENABLED"] = "false"
    env.pop("PUBLIC_TUNNEL_RESERVED_ORIGIN", None)
    return env


def preflight(env: dict[str, str], *, line: bool, ports: bool = True) -> list[str]:
    problems = []
    settings = Settings(_env_file=None, **{key.lower(): value for key, value in env.items()})
    try:
        require_local_demo(settings.app_env, settings.database_url)
        from urllib.parse import urlsplit

        if urlsplit(settings.minio_endpoint).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("local MinIO required")
    except ValueError:
        problems.append("只支援 APP_ENV=local/test、loopback strayhub 資料庫與本機 MinIO。")
    commands = ["docker", "npm", "uv"]
    if line:
        commands += [env.get("NGINX_BIN", "nginx"), "ngrok", "curl", "python3", "openssl"]
        for name in (
            "NGROK_URL",
            "LIFF_ID",
            "LINE_LOGIN_CHANNEL_ID",
            "LINE_CHANNEL_SECRET",
            "LINE_CHANNEL_ACCESS_TOKEN",
        ):
            value = env.get(name, "")
            if not value or value.startswith("fake-") or "your-reserved-domain" in value:
                problems.append(f"LINE 模式缺少真實 {name}，請設定 .env。")
        from services.api.app.application.media_access import public_https_url_or_none

        if not public_https_url_or_none(env.get("NGROK_URL"), origin_only=True):
            problems.append("NGROK_URL 必須是固定公開 HTTPS origin。")
    for command in commands:
        if not shutil.which(command):
            problems.append(f"缺少命令：{command}")
    if shutil.which("docker"):
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=15)
        if result.returncode:
            problems.append("Docker 尚未啟動或無法連線，請先啟動 Docker Desktop。")
    if line and shutil.which("ngrok"):
        if subprocess.run(["ngrok", "config", "check"], capture_output=True, timeout=15).returncode:
            problems.append("ngrok 尚未完成本機帳號授權。")
    names = ["API_PORT", "WEB_PORT"] + (["NGINX_PORT"] if line else [])
    for name in names if ports else []:
        try:
            port = int(env[name])
            if not 1 <= port <= 65535:
                raise ValueError
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        except (OSError, ValueError):
            problems.append(f"{name} 無效或已被使用，請先停止舊服務或修改 .env。")
    if ports and len({env[name] for name in names}) != len(names):
        problems.append("API、Web 與 gateway 必須使用不同連接埠。")
    return problems


def save_private(path: Path, payload: dict) -> None:
    if path.is_symlink():
        raise RuntimeError("本機狀態檔不可為 symbolic link。")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(payload, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def persistent_keys(env: dict[str, str], *, encrypted_data: bool) -> None:
    if KEYS.is_symlink():
        raise RuntimeError("開發金鑰檔不可為 symbolic link。")
    saved = json.loads(KEYS.read_text()) if KEYS.exists() else {}
    for name, value in saved.items():
        if env.get(name) and env[name] != value:
            raise RuntimeError(f"{name} 與已保存的開發金鑰不同；請明確處理金鑰輪替。")
        env[name] = value
    private, public = "AUTH_JWT_ACTIVE_PRIVATE_KEY", "AUTH_JWT_ACTIVE_PUBLIC_KEY"
    if bool(env.get(private)) != bool(env.get(public)):
        raise RuntimeError("JWT 私鑰與公鑰必須成對設定。")
    if not env.get("PII_LOCAL_KEY_BASE64") and encrypted_data:
        raise RuntimeError("既有加密資料缺少 PII 金鑰，請還原原本的 PII_LOCAL_KEY_BASE64。")
    if not env.get(private):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        env[private] = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        env[public] = (
            key.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
    if not env.get("PII_LOCAL_KEY_BASE64"):
        env["PII_LOCAL_KEY_BASE64"] = base64.b64encode(secrets.token_bytes(32)).decode()
    if len(base64.b64decode(env["PII_LOCAL_KEY_BASE64"], validate=True)) != 32:
        raise RuntimeError("PII_LOCAL_KEY_BASE64 必須是 base64 編碼的 32-byte 金鑰。")
    loaded = serialization.load_pem_private_key(env[private].encode(), password=None)
    expected = loaded.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    if expected.strip() != env[public].encode().strip():
        raise RuntimeError("JWT 公鑰與私鑰不匹配。")
    env["PII_ALLOW_LOCAL_PROVIDER"] = "true"
    save_private(KEYS, {name: env[name] for name in (private, public, "PII_LOCAL_KEY_BASE64")})


async def database_state(url: str) -> dict:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SELECT set_config('app.platform_scope', 'true', true)"))
            users = set(
                (
                    await connection.scalars(
                        text("SELECT username FROM users WHERE username = ANY(:names)"),
                        {"names": list(ACCOUNTS)},
                    )
                ).all()
            )
            orgs = set((await connection.scalars(text("SELECT code FROM organizations"))).all())
            total_users = await connection.scalar(text("SELECT count(*) FROM users"))
            organization_ids = (
                await connection.scalars(text("SELECT id FROM organizations"))
            ).all()
            encrypted = False
            from services.api.app.persistence.database.scope import set_organization_scope

            for organization_id in organization_ids:
                await set_organization_scope(connection, organization_id)
                encrypted = encrypted or bool(
                    await connection.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM volunteer_application_profiles "
                            "WHERE organization_id=:org AND applicant_name_ciphertext IS NOT NULL)"
                        ),
                        {"org": organization_id},
                    )
                )
            return {
                "users": users,
                "orgs": orgs,
                "encrypted": encrypted,
                "total_users": total_users,
            }
    finally:
        await engine.dispose()


def needs_bootstrap(state: dict) -> bool:
    if set(ACCOUNTS) <= state["users"] and set(DEMO_SHELTERS) <= state["orgs"]:
        return False
    if state["total_users"] or state["orgs"]:
        raise RuntimeError(
            "資料庫已有資料但 demo 帳號／收容所不完整；保留現況。"
            "如要明確重新初始化 demo，請執行 ./scripts/demo.sh check。"
        )
    return True


def read_password() -> str:
    supplied = os.environ.get("STRAYHUB_DEMO_PASSWORD")
    if supplied:
        return require_demo_password(supplied)
    if not sys.stdin.isatty():
        raise RuntimeError("初始化／重設密碼需要互動終端機或 STRAYHUB_DEMO_PASSWORD。")
    while True:
        value = getpass.getpass("設定開發密碼（至少 16 字元，只需設定一次）：")
        try:
            return require_demo_password(value)
        except ValueError:
            print("密碼需至少 16 字元，且不可使用已停用的舊 demo 密碼。")


async def reset_password(url: str, password: str) -> None:
    from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher

    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            # Update only known demo identities; preserve roles, grants, data and LINE bindings.
            ids = (
                await connection.scalars(
                    text("SELECT id FROM users WHERE username = ANY(:names)"),
                    {"names": list(ACCOUNTS)},
                )
            ).all()
            if len(ids) != len(ACCOUNTS):
                raise RuntimeError("Demo 帳號不完整，請先完成初始化。")
            await connection.execute(
                text("UPDATE users SET password_hash=:hash WHERE id=ANY(:ids)"),
                {"hash": Argon2PasswordHasher().hash(password), "ids": ids},
            )
            await connection.execute(
                text(
                    "UPDATE session_records SET status='expired', expires_at=now() "
                    "WHERE user_id=ANY(:ids) AND status='active'"
                ),
                {"ids": ids},
            )
    finally:
        await engine.dispose()


class Processes:
    def __init__(self, env: dict[str, str]):
        self.env = env
        self.children: list[tuple[str, subprocess.Popen]] = []

    def start(self, label: str, args: list[str]) -> subprocess.Popen:
        process = subprocess.Popen(args, cwd=ROOT, env=self.env, start_new_session=True)
        self.children.append((label, process))
        return process

    def check(self) -> None:
        for label, child in self.children:
            if child.poll() is not None:
                raise RuntimeError(f"{label} 已停止（exit {child.returncode}）。")

    def ready(self, url: str, timeout: int = 120) -> None:
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            self.check()
            try:
                with urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        return
            except (URLError, OSError):
                pass
            time.sleep(0.5)
        raise RuntimeError("服務啟動逾時，請檢查上方服務日誌。")

    def close(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            for _, child in reversed(self.children):
                try:
                    os.killpg(child.pid, sig)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    # macOS can report EPERM for a group whose reaped leader no longer exists.
                    if child.poll() is None:
                        raise
            if sig == signal.SIGTERM:
                time.sleep(1)
        for _, child in self.children:
            child.wait()
        self.children.clear()


def run(args: list[str], env: dict[str, str]) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def launch(env: dict[str, str], *, line: bool) -> None:
    processes = Processes(env)
    try:
        if line:
            processes.start("LINE 開發服務", ["bash", "scripts/demo-line.sh", "--developer"])
        else:
            processes.start(
                "API",
                [
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "uvicorn",
                    "services.api.app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    env["API_PORT"],
                    "--reload",
                    "--reload-dir",
                    "services/api",
                ],
            )
            processes.ready(f"{env['API_BASE_URL']}/healthz")
            processes.start(
                "Web",
                [
                    "npm",
                    "--prefix",
                    "apps/web",
                    "run",
                    "dev",
                    "--",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    env["WEB_PORT"],
                ],
            )
            if env.get("START_WORKER", "1") == "1":
                processes.start("Worker", ["uv", "run", "python", "-m", "services.worker.worker"])
        processes.ready(f"http://127.0.0.1:{env['WEB_PORT']}/login", timeout=240)
        print(f"\n本機管理介面：http://127.0.0.1:{env['WEB_PORT']}/login", flush=True)
        print("收容所管理員：demo-furkids-admin；平台管理員：demo-platform-admin", flush=True)
        print(
            "志工：demo-furkids-volunteer／demo-xindian-volunteer／demo-wugu-volunteer", flush=True
        )
        print("密碼沿用既有設定；Ctrl-C 停止應用服務，資料保留。", flush=True)
        while True:
            processes.check()
            time.sleep(0.5)
    finally:
        processes.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", nargs="?", default="start", choices=["start", "doctor", "password"]
    )
    parser.add_argument("--line", action="store_true", help="同時啟用真實 LINE／LIFF tunnel")
    args = parser.parse_args()
    os.chdir(ROOT)
    env = configuration()
    problems = preflight(env, line=args.line, ports=args.command != "password")
    if problems:
        raise RuntimeError("\n".join(problems))
    if args.command == "doctor":
        print("工具、Docker、設定與連接埠檢查通過；不修改資料或啟動 tunnel。")
        return
    # flock survives only while this process is alive, including crash recovery.
    with (ROOT / ".env.dev.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("已有開發 helper 執行中，請使用既有入口或先按 Ctrl-C。") from None
        prepare_and_launch(env, command=args.command, line=args.line)


def prepare_and_launch(env: dict[str, str], *, command: str, line: bool) -> None:
    if not (ROOT / ".env").exists():
        shutil.copyfile(ROOT / ".env.example", ROOT / ".env")
        env = configuration()
    settings = Settings(_env_file=None, **{key.lower(): value for key, value in env.items()})
    env["DATABASE_URL"] = settings.database_url
    run(COMPOSE + ["up", "-d", "--wait", "postgres", "minio"], env)
    run(["uv", "run", "alembic", "upgrade", "head"], env)
    run(["uv", "run", "python", "-m", "scripts.configure_runtime_role", "--apply"], env)
    state = asyncio.run(database_state(settings.database_url))
    if command == "password":
        asyncio.run(reset_password(settings.database_url, read_password()))
        print("Demo 密碼已更新，舊 session 已失效；角色、資料及 LINE 綁定保留。")
        return
    initialize = needs_bootstrap(state)
    persistent_keys(env, encrypted_data=state["encrypted"])
    if initialize:
        env["STRAYHUB_DEMO_PASSWORD"] = read_password()
        print("首次初始化三收容所 demo，照片下載可能需要幾分鐘。", flush=True)
        run(["uv", "run", "python", "-m", "scripts.bootstrap_demo"], env)
    else:
        print("沿用既有帳號、資料及 LINE 綁定；不執行 seed。", flush=True)
    env.pop("STRAYHUB_DEMO_PASSWORD", None)
    digest = hashlib.sha256((ROOT / "apps/web/package-lock.json").read_bytes()).hexdigest()
    saved = json.loads(STATE.read_text()) if STATE.exists() else {}
    if not (ROOT / "apps/web/node_modules").exists() or saved.get("web_lock") != digest:
        run(["npm", "ci", "--prefix", "apps/web"], env)
        save_private(STATE, {"web_lock": digest})
    launch(env, line=line)


if __name__ == "__main__":

    def stop(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        main()
    except KeyboardInterrupt:
        print("\n開發服務已停止，資料保留。")
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError, SQLAlchemyError) as exc:
        # Third-party exceptions can contain connection credentials; keep them out of output.
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f"開發環境未就緒：{message}", file=sys.stderr)
        sys.exit(1)
