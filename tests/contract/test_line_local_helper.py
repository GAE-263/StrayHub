from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/test_line_local.sh"
NGINX_TEMPLATE = ROOT / "infra/local/nginx/line-local.conf.template"
ALLOWLIST = (
    ROOT / "specs/012-sensitive-data-transport-hardening/contracts/line-tunnel-allowlist.yaml"
)


def _allowlist() -> dict:
    return yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8"))


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


def test_local_nginx_routes_only_allowlisted_api_and_web_paths() -> None:
    source = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert "listen 127.0.0.1:__NGINX_PORT__;" in source
    assert "server 127.0.0.1:__API_PORT__;" in source
    assert "server 127.0.0.1:__WEB_PORT__;" in source
    assert "location = /healthz" not in source
    assert "location ^~ /v1/" not in source
    assert "location = /volunteer-application" in source
    assert 'location ~ "^/_next/static/[A-Za-z0-9_./-]+$"' in source
    assert "location = /_next/webpack-hmr" in source
    assert "location ^~ /_next/ {" not in source
    assert "location /" in source
    assert "proxy_pass http://strayhub_api;" in source
    assert "proxy_pass http://strayhub_api/;" not in source
    assert "proxy_pass http://strayhub_web;" in source

    default_location = source.split("location / {", 1)[1].split("}", 1)[0]
    assert "return 404;" in default_location
    assert "proxy_pass" not in default_location


def test_line_tunnel_allowlist_is_complete_and_has_no_broad_forwarding_rule() -> None:
    policy = _allowlist()
    assert policy["default_action"] == "deny"
    assert policy["policy"]["rejection_status"] == 404
    routes = policy["routes"]
    ids = [route["id"] for route in routes]
    assert len(ids) == len(set(ids))
    assert all(route.get("methods") for route in routes)
    assert all(route.get("owner") and route.get("reason") for route in routes)
    assert all(route.get("evidence") and route.get("tests") for route in routes)
    assert all(("path" in route) ^ ("path_pattern" in route) for route in routes)
    assert not any(route.get("path") in {"/", "/v1/**", "/_next/**"} for route in routes)

    source = NGINX_TEMPLATE.read_text(encoding="utf-8")
    for route_id in ids:
        assert f"allowlist: {route_id}" in source


def test_local_nginx_default_deny_matrix_and_method_boundaries() -> None:
    source = NGINX_TEMPLATE.read_text(encoding="utf-8")
    for forbidden in (
        "location = /login",
        "location ^~ /v1/management/",
        "location = /openapi.json",
        "location = /docs",
        "location ~ ^/assigned-care/",
    ):
        assert forbidden not in source
    assert "if ($request_method" in source
    assert "return 404;" in source
    assert "error_page 404 = @" not in source


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

    api_location = source.split("# allowlist: line_webhook", 1)[1].split("\n        }", 1)[0]
    assert "strayhub_api" in api_location
    assert "strayhub_web" not in api_location
    next_location = source.split("# allowlist: next_static_assets", 1)[1].split("\n        }", 1)[0]
    assert "^/_next/static/[A-Za-z0-9_./-]+$" in next_location
    assert "strayhub_web" in next_location
    assert "strayhub_api" not in next_location


def test_local_nginx_uses_safe_logging_for_every_sensitive_route_group() -> None:
    source = NGINX_TEMPLATE.read_text(encoding="utf-8")
    sensitive_format = source.split("log_format strayhub_sensitive", 1)[1].split(";", 1)[0]
    standard_format = source.split("log_format strayhub_standard", 1)[1].split(";", 1)[0]

    for route_pattern in (
        "~^/(login|volunteer-entry|volunteer-application|animal-confirmation)/?$ 1;",
        "~^/v1/auth/(login|refresh|liff/exchange)/?$ 1;",
        "~^/v1/public/(adoption/)?animals/[^/]+/photo/?$ 1;",
    ):
        assert route_pattern in source
    assert "$request_method $uri $server_protocol" in sensitive_format
    for unsafe in ("$args", "$request_uri", '"$request"', "$http_referer"):
        assert unsafe not in sensitive_format
    assert '"$request"' in standard_format
    assert "$http_referer" in standard_format
    assert "access_log logs/access.log strayhub_sensitive " in source
    assert "if=$strayhub_sensitive_access;" in source


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
    assert "addr: 127.0.0.1:${NGINX_LOCAL_PORT}" in source
    assert "addr: 127.0.0.1:${WEB_LOCAL_PORT}" not in source


def test_line_local_helper_smokes_default_deny_before_tunnel_start() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    deny_loop = "for denied_path in /login /v1/management/dashboard /v1/not-allowlisted"
    assert deny_loop in source
    assert '"$PROXY_LOCAL_URL${denied_path}"' in source
    assert source.index(deny_loop) < source.index("require_command ngrok")


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
