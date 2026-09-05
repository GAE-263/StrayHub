from __future__ import annotations

import http.client
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "infra/local/nginx/line-local.conf.template"
ALLOWLIST = (
    ROOT / "specs/012-sensitive-data-transport-hardening/contracts/line-tunnel-allowlist.yaml"
)
UUID = "11111111-1111-4111-8111-111111111111"


class _RecordingHandler(BaseHTTPRequestHandler):
    records: list[tuple[str, str]] = []
    upstream = "unknown"

    def _respond(self) -> None:
        self.__class__.records.append((self.command, self.path))
        if self.path.split("?", 1)[0] == "/v1/line/webhook":
            status = 200 if self.headers.get("X-Line-Signature") == "synthetic-valid" else 401
        else:
            status = 200
        body = f"{self.upstream}:{self.command}:{self.path}".encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_GET = _respond
    do_HEAD = _respond
    do_POST = _respond
    do_PUT = _respond
    do_PATCH = _respond

    def log_message(self, format: str, *args: object) -> None:
        return


class _ApiHandler(_RecordingHandler):
    records: list[tuple[str, str]] = []
    upstream = "api"


class _WebHandler(_RecordingHandler):
    records: list[tuple[str, str]] = []
    upstream = "web"


def _server(handler: type[_RecordingHandler]) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request(
    port: int,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    connection.request(method, path, headers=headers or {})
    response = connection.getresponse()
    body = response.read().decode(errors="replace")
    connection.close()
    return response.status, body


def _sample_path(route: dict) -> str:
    if "path" in route:
        return route["path"]
    return {
        "next_static_assets": (
            "/_next/static/chunks/app/(volunteer-onboarding)/volunteer-application/page.js"
        ),
        "volunteer_application_withdraw": f"/v1/volunteer-applications/{UUID}/withdraw",
        "animal_confirm": f"/v1/animals/{UUID}/confirm",
        "update_care_report_draft": f"/v1/care-report-drafts/{UUID}",
        "volunteer_walk_photo": f"/v1/public/animals/{UUID}/photo",
        "public_adoption_photo": f"/v1/public/adoption/animals/{UUID}/photo",
    }[route["id"]]


def test_public_gateway_runtime_allow_deny_and_query_preservation(tmp_path: Path) -> None:
    nginx_binary = shutil.which("nginx")
    assert nginx_binary is not None, "nginx is required for the public gateway runtime gate"
    api, api_thread = _server(_ApiHandler)
    web, web_thread = _server(_WebHandler)
    gateway_port = _free_port()
    prefix = tmp_path / "nginx"
    (prefix / "logs").mkdir(parents=True)
    config = TEMPLATE.read_text(encoding="utf-8")
    config = config.replace("__API_PORT__", str(api.server_port))
    config = config.replace("__WEB_PORT__", str(web.server_port))
    config = config.replace("__NGINX_PORT__", str(gateway_port))
    config_path = prefix / "line-local.conf"
    config_path.write_text(config, encoding="utf-8")
    nginx = subprocess.Popen(
        [
            nginx_binary,
            "-p",
            f"{prefix}/",
            "-c",
            str(config_path),
            "-g",
            "daemon off;",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(40):
            try:
                if _request(gateway_port, "GET", "/volunteer-entry")[0] == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            _, error = nginx.communicate(timeout=2)
            raise AssertionError(f"nginx gateway did not start: {error}")

        policy = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8"))
        for route in policy["routes"]:
            path = _sample_path(route) + "?token=class-b-negative-control&page=2"
            for method in route["methods"]:
                headers = (
                    {"X-Line-Signature": "synthetic-valid"}
                    if route["id"] == "line_webhook"
                    else None
                )
                status, body = _request(gateway_port, method, path, headers=headers)
                assert status == 200, (route["id"], method)
                if method != "HEAD":
                    assert "token=class-b-negative-control&page=2" in body
                    assert body.startswith(f"{route['upstream']}:")

        assert _request(gateway_port, "POST", "/v1/line/webhook")[0] == 401
        assert (
            _request(
                gateway_port,
                "POST",
                "/v1/line/webhook",
                headers={"X-Line-Signature": "synthetic-invalid"},
            )[0]
            == 401
        )

        denied = (
            "/",
            "/login?password=deny-boundary-sentinel",
            "/animals",
            "/reports",
            "/platform-admins",
            f"/assigned-care/{UUID}",
            "/v1/auth/login",
            "/v1/management/dashboard",
            "/v1/platform/administrators",
            "/v1/organizations",
            "/v1/not-allowlisted",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/_next/image?url=deny-boundary-sentinel",
            "/_next/server-internal",
            "/_next/static/chunks/app/%2e%2e/%2e%2e/%2e%2e/login",
            "/volunteer-entry%2F..%2Flogin",
        )
        api_before = len(_ApiHandler.records)
        web_before = len(_WebHandler.records)
        for path in denied:
            status, body = _request(gateway_port, "GET", path)
            assert status in {400, 404}, path
            assert "deny-boundary-sentinel" not in body
        assert len(_ApiHandler.records) == api_before
        assert len(_WebHandler.records) == web_before

        assert _request(gateway_port, "GET", "/v1/line/webhook")[0] == 404
        assert _request(gateway_port, "POST", "/volunteer-entry")[0] == 404
        assert _request(gateway_port, "POST", "/v1/animals/search")[0] == 404
    finally:
        nginx.terminate()
        try:
            nginx.wait(timeout=5)
        except subprocess.TimeoutExpired:
            nginx.kill()
            nginx.wait(timeout=5)
        api.shutdown()
        web.shutdown()
        api.server_close()
        web.server_close()
        api_thread.join(timeout=2)
        web_thread.join(timeout=2)
