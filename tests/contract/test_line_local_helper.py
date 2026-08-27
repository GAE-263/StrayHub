from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/test_line_local.sh"
NGINX_TEMPLATE = ROOT / "infra/local/nginx/line-local.conf.template"


def test_line_local_helper_is_executable_and_resolves_current_repo_contract() -> None:
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)

    result = subprocess.run(
        [str(SCRIPT), "--print-env"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "API_LOCAL_PORT=8001" in result.stdout
    assert "WEB_LOCAL_PORT=3001" in result.stdout
    assert "NGINX_LOCAL_PORT=8082" in result.stdout
    assert "LINE_WEBHOOK_ROUTE=/v1/line/webhook" in result.stdout
    assert "LIFF_ROUTE=/volunteer-application" in result.stdout
    assert "FRONTEND_API_ENV=API_BASE_URL" in result.stdout
    assert "LIFF_ID_ENV=LIFF_ID" in result.stdout
    assert "ALLOWED_DEV_ORIGIN_ENV=LINE_DEMO_WEB_ORIGIN_HOST" in result.stdout
    assert "NGINX_TEMPLATE=infra/local/nginx/line-local.conf.template" in result.stdout


def test_local_nginx_routes_api_and_web_without_stripping_paths() -> None:
    source = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert "listen 127.0.0.1:__NGINX_PORT__;" in source
    assert "server 127.0.0.1:__API_PORT__;" in source
    assert "server 127.0.0.1:__WEB_PORT__;" in source
    assert "location = /healthz" in source
    assert "location ^~ /v1/" in source
    assert "location = /volunteer-application" in source
    assert "location ^~ /_next/" in source
    assert "location /" in source
    assert "proxy_pass http://strayhub_api;" in source
    assert "proxy_pass http://strayhub_api/;" not in source
    assert "proxy_pass http://strayhub_web;" in source


def test_local_nginx_configures_forwarded_and_websocket_headers() -> None:
    source = NGINX_TEMPLATE.read_text(encoding="utf-8")

    for required in (
        "proxy_http_version 1.1;",
        "proxy_set_header Host $http_host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "proxy_set_header X-Forwarded-Proto $forwarded_proto;",
        "proxy_set_header Upgrade $http_upgrade;",
        "proxy_set_header Connection $connection_upgrade;",
    ):
        assert required in source

    api_location = source.split("location ^~ /v1/", 1)[1].split("}", 1)[0]
    assert "strayhub_api" in api_location
    assert "strayhub_web" not in api_location
    next_location = source.split("location ^~ /_next/", 1)[1].split("}", 1)[0]
    assert "strayhub_web" in next_location
    assert "strayhub_api" not in next_location
    assert "Upgrade $http_upgrade" in next_location


def test_line_local_helper_owns_one_named_tunnel_without_weakening_security() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for required in (
        "set -Eeuo pipefail",
        "strayhub-single-origin:",
        "addr: 127.0.0.1:${NGINX_LOCAL_PORT}",
        "http://127.0.0.1:4040/api/tunnels",
        'by_name.get("strayhub-single-origin", "")',
        "attempt <= 20",
        "X-Line-Signature",
        "tests/security/test_line_webhook_signature.py",
        "nginx → Web HMR WebSocket",
        "Sec-WebSocket-Key",
        "--no-tunnel",
        "--print-env",
        'MODE" == "stop"',
        "pid_is_owned_ngrok",
        "pid_is_owned_nginx",
        "ngrok config check",
    ):
        assert required in source

    for removed in (
        "API_PUBLIC_URL",
        "WEB_PUBLIC_URL",
        "strayhub-api:",
        "strayhub-web:",
        "ngrok start strayhub-api strayhub-web",
    ):
        assert removed not in source

    assert "pkill" not in source
    assert "killall" not in source
    assert "source .env" not in source
    assert 'allow_origins=["*"]' not in source
    assert "sync_line_rich_menu.py --apply" not in source
    assert "LINE_CHANNEL_SECRET=${LINE_CHANNEL_SECRET}" not in source
    assert "LINE_CHANNEL_ACCESS_TOKEN=${LINE_CHANNEL_ACCESS_TOKEN}" not in source


def test_line_local_helper_keeps_single_tunnel_discovery_order_independent() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'by_name = {item.get("name"): item.get("public_url", "")' in source
    assert "tunnels[0]" not in source
    assert "tunnels[1]" not in source


def test_line_local_helper_prints_one_shared_origin_configuration() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for required in (
        "Local direct",
        "Local nginx",
        "Public",
        "Webhook URL:",
        "LIFF Endpoint URL:",
        "Rich Menu LIFF URI:",
        "Frontend API base:",
        "Next.js allowed dev origin:",
        "${PUBLIC_URL}${LINE_WEBHOOK_ROUTE}",
        "${PUBLIC_URL}${LIFF_ROUTE}",
        "${FRONTEND_API_ENV}=${PUBLIC_URL}",
        "${ORIGIN_ENV}=${PUBLIC_HOST}",
    ):
        assert required in source

    assert 'PUBLIC_HOST="${PUBLIC_URL#https://}"' in source
    assert "Public tunnels" not in source


def test_line_local_helper_never_prints_supplied_secret_values() -> None:
    sentinel_secret = "controlled-secret-value-that-must-not-appear"
    environment = {
        **os.environ,
        "LINE_CHANNEL_SECRET": sentinel_secret,
        "LINE_CHANNEL_ACCESS_TOKEN": f"{sentinel_secret}-token",
        "LINE_LOGIN_CHANNEL_ID": "real-login-channel",
        "LIFF_ID": "real-liff-id",
        "API_PORT": "65534",
        "WEB_PORT": "65533",
    }

    result = subprocess.run(
        [str(SCRIPT), "--no-tunnel"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert sentinel_secret not in result.stdout
    assert sentinel_secret not in result.stderr


def test_stop_does_not_kill_processes_not_owned_by_helper(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "strayhub-line-local-test"
    nginx_dir = runtime_dir / "nginx"
    nginx_dir.mkdir(parents=True)
    unrelated_ngrok = subprocess.Popen(["sleep", "30"])
    unrelated_nginx = subprocess.Popen(["sleep", "30"])
    try:
        (runtime_dir / "ngrok.pid").write_text(f"{unrelated_ngrok.pid}\n", encoding="utf-8")
        (nginx_dir / "nginx.pid").write_text(f"{unrelated_nginx.pid}\n", encoding="utf-8")
        result = subprocess.run(
            [str(SCRIPT), "stop"],
            cwd=ROOT,
            env={**os.environ, "TMPDIR": str(tmp_path)},
            check=True,
            capture_output=True,
            text=True,
        )

        assert unrelated_ngrok.poll() is None
        assert unrelated_nginx.poll() is None
        assert result.stdout.count("nothing killed") == 2
    finally:
        unrelated_ngrok.terminate()
        unrelated_nginx.terminate()
        unrelated_ngrok.wait(timeout=5)
        unrelated_nginx.wait(timeout=5)
