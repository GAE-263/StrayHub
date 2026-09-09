from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from uuid import uuid4

import pytest
from scripts import dev
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter


def complete_state():
    return {
        "users": set(dev.ACCOUNTS),
        "orgs": set(dev.DEMO_SHELTERS),
        "encrypted": False,
        "total_users": len(dev.ACCOUNTS),
    }


def test_restart_preserves_signing_and_encryption_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "KEYS", tmp_path / "keys.json")
    first = {}
    dev.persistent_keys(first, encrypted_data=False)
    issuer = JwtAccessTokenAdapter(
        issuer="test",
        audience="test",
        active_kid="dev",
        private_key=first["AUTH_JWT_ACTIVE_PRIVATE_KEY"],
        public_keys={"dev": first["AUTH_JWT_ACTIVE_PUBLIC_KEY"]},
    )
    token = issuer.issue({"sub": str(uuid4()), "sid": str(uuid4())})
    second = {}
    dev.persistent_keys(second, encrypted_data=True)
    verifier = JwtAccessTokenAdapter(
        issuer="test",
        audience="test",
        active_kid="dev",
        private_key=second["AUTH_JWT_ACTIVE_PRIVATE_KEY"],
        public_keys={"dev": second["AUTH_JWT_ACTIVE_PUBLIC_KEY"]},
    )
    assert verifier.verify(token)["typ"] == "access"
    assert first == second
    assert dev.KEYS.stat().st_mode & 0o777 == 0o600
    assert "PASSWORD" not in dev.KEYS.read_text()


def test_missing_encryption_key_never_replaces_existing_data_key(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "KEYS", tmp_path / "keys.json")
    with pytest.raises(RuntimeError, match="還原原本"):
        dev.persistent_keys({}, encrypted_data=True)
    assert not dev.KEYS.exists()


def test_key_conflict_does_not_overwrite_saved_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "KEYS", tmp_path / "keys.json")
    dev.persistent_keys({}, encrypted_data=False)
    before = dev.KEYS.read_bytes()
    with pytest.raises(RuntimeError, match="輪替"):
        dev.persistent_keys({"PII_LOCAL_KEY_BASE64": "different"}, encrypted_data=True)
    assert dev.KEYS.read_bytes() == before


def test_partial_dataset_is_not_silently_reseeded():
    assert not dev.needs_bootstrap(complete_state())
    assert dev.needs_bootstrap({"users": set(), "orgs": set(), "total_users": 0})
    partial = complete_state()
    partial["users"].remove("demo-platform-admin")
    with pytest.raises(RuntimeError, match="保留現況"):
        dev.needs_bootstrap(partial)


@pytest.mark.parametrize("line", [False, True])
def test_daily_start_never_seeds_or_asks_password(tmp_path, monkeypatch, line):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("APP_ENV=local\n")
    web = tmp_path / "apps/web"
    (web / "node_modules").mkdir(parents=True)
    (web / "package-lock.json").write_text("{}")
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "STATE", tmp_path / "state.json")
    dev.STATE.write_text(json.dumps({"web_lock": dev.hashlib.sha256(b"{}").hexdigest()}))
    monkeypatch.setattr(dev, "preflight", lambda *a, **k: [])
    monkeypatch.setattr(
        dev,
        "configuration",
        lambda: {"APP_ENV": "local", "DATABASE_URL": "postgresql+asyncpg://x@127.0.0.1/strayhub"},
    )

    async def state(_url):
        return complete_state()

    monkeypatch.setattr(dev, "database_state", state)
    monkeypatch.setattr(dev, "persistent_keys", lambda *a, **k: None)
    monkeypatch.setattr(dev, "read_password", lambda: pytest.fail("restart prompted for password"))
    commands = []
    monkeypatch.setattr(dev, "run", lambda args, env: commands.append(args))
    launched = []
    monkeypatch.setattr(dev, "launch", lambda env, **kw: launched.append(kw))
    monkeypatch.setattr(sys, "argv", ["dev"] + (["--line"] if line else []))
    dev.main()
    assert launched == [{"line": line}]
    assert not any("bootstrap_demo" in " ".join(cmd) or "npm" in cmd for cmd in commands)


def test_configuration_keeps_local_web_and_line_on_same_private_upstream(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "API_PORT=8211\nWEB_PORT=3211\nLOGIN_TRUSTED_PROXY_ENABLED=true\n"
    )
    monkeypatch.delenv("API_PORT", raising=False)
    monkeypatch.delenv("WEB_PORT", raising=False)
    env = dev.configuration()
    assert env["API_BASE_URL"] == "http://127.0.0.1:8211"
    assert env["API_HOST"] == env["WEB_HOST"] == "127.0.0.1"
    assert env["LOGIN_TRUSTED_PROXY_ENABLED"] == "false"


def test_supervisor_stops_owned_process_group_and_preserves_other_processes(tmp_path):
    supervisor = dev.Processes(dict(os.environ))
    other = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
    )
    try:
        child = supervisor.start("worker", [sys.executable, "-c", "import time; time.sleep(60)"])
        exited = supervisor.start("failed", [sys.executable, "-c", "raise SystemExit(2)"])
        exited.wait(timeout=5)
        with pytest.raises(RuntimeError, match="failed"):
            supervisor.check()
        supervisor.close()
        assert child.poll() is not None
        assert other.poll() is None
    finally:
        supervisor.close()
        os.killpg(other.pid, signal.SIGTERM)
        other.wait(timeout=5)


def test_line_developer_mode_cannot_select_shared_profile():
    result = subprocess.run(
        ["bash", "scripts/demo-line.sh", "--developer", "--profile", "shared-demo-dev"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert "line-only" in result.stderr


def test_port_check_retries_transient_shutdown(monkeypatch):
    attempts = {3001: 0, 8001: 0}

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def bind(self, address):
            port = address[1]
            attempts[port] += 1
            if port == 3001 and attempts[port] < 3:
                raise OSError("still stopping")
            if port == 8001:
                raise OSError("owned by another service")

    monkeypatch.setattr(dev.socket, "socket", Probe)
    monkeypatch.setattr(dev.time, "sleep", lambda _seconds: None)

    assert dev.wait_for_ports({"WEB_PORT": 3001, "API_PORT": 8001}) == {"API_PORT": 8001}
    assert attempts[3001] == 3
    assert attempts[8001] == 13
