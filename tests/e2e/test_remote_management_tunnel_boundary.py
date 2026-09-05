from __future__ import annotations

import http.client
import shutil
import socket
import subprocess
import threading
import time
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from scripts.generate_public_tunnel_config import generate_runtime_configs

FIXTURE_BUILD = Path("tests/security/fixtures/next-manifests")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ProbeHandler(BaseHTTPRequestHandler):
    counts: Counter[tuple[str, str]] = Counter()
    received_headers: dict[str, str] = {}

    def _reply(self) -> None:
        type(self).counts[(self.command, self.path)] += 1
        type(self).received_headers = {key.lower(): value for key, value in self.headers.items()}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"upstream")

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = _reply

    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def gateway(profile: str, tmp_path: Path):
    if shutil.which("nginx") is None:
        pytest.skip("nginx is not installed")
    api_port, web_port, gateway_port = free_port(), free_port(), free_port()
    ProbeHandler.counts.clear()
    servers = [
        ThreadingHTTPServer(("127.0.0.1", api_port), ProbeHandler),
        ThreadingHTTPServer(("127.0.0.1", web_port), ProbeHandler),
    ]
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    origin = f"http://127.0.0.1:{gateway_port}" if profile != "line-only" else None
    result = generate_runtime_configs(
        profile_name=profile,
        output_dir=tmp_path,
        api_port=api_port,
        web_port=web_port,
        gateway_port=gateway_port,
        build_dir=FIXTURE_BUILD if profile == "shared-demo-production" else None,
        runtime_origin=origin,
        allow_loopback_for_test=True,
    )
    process = subprocess.Popen(
        [
            "nginx",
            "-p",
            f"{tmp_path}/",
            "-c",
            str(result.nginx_path),
            "-g",
            "daemon off;",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", gateway_port), timeout=0.1):
                break
        except OSError:
            if process.poll() is not None:
                _, stderr = process.communicate()
                raise AssertionError(stderr) from None
            time.sleep(0.02)
    try:
        yield gateway_port
    finally:
        process.terminate()
        process.wait(timeout=5)
        for server in servers:
            server.shutdown()
            server.server_close()


def request(
    port: int,
    method: str,
    path: str,
    *,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    request_headers = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    connection.request(method, path, headers=request_headers)
    response = connection.getresponse()
    response.read()
    connection.close()
    return response.status


@pytest.mark.parametrize("profile", ["shared-demo-production", "shared-demo-dev"])
def test_shared_profiles_allow_only_reviewed_management_surface(
    profile: str, tmp_path: Path
) -> None:
    with gateway(profile, tmp_path) as port:
        assert request(port, "GET", "/login") == 200
        assert request(port, "POST", "/v1/auth/login") == 200
        assert ProbeHandler.received_headers["x-strayhub-public-profile"] == profile
        assert (
            request(
                port,
                "GET",
                "/v1/auth/me",
                headers={"X-StrayHub-Public-Profile": "attacker-controlled"},
            )
            == 200
        )
        assert ProbeHandler.received_headers["x-strayhub-public-profile"] == profile
        count = sum(ProbeHandler.counts.values())
        assert request(port, "GET", "/v1/not-allowlisted") == 404
        assert request(port, "GET", "/v1/platform/admins") == 404
        assert request(port, "GET", "/platform-admins") == 404
        assert request(port, "GET", "/docs") == 404
        assert request(port, "GET", "/redoc") == 404
        assert request(port, "GET", "/openapi.json") == 404
        assert request(port, "GET", "/debug/config") == 404
        assert request(port, "GET", "/internal/health") == 404
        assert request(port, "GET", "/settings/audit") == 404
        assert request(port, "GET", "/animals/not-a-uuid") == 404
        assert request(port, "POST", "/v1/management/reports") == 404
        assert request(port, "GET", "/_rsc?value=anything") == 404
        assert request(port, "GET", "/v1//management/reports") == 404
        assert request(port, "GET", "/v1%2Fmanagement/reports") == 404
        assert request(port, "GET", "/v1/management/../platform/admins") == 404
        assert sum(ProbeHandler.counts.values()) == count
        assert request(port, "GET", "/v1/management/reports?status=new") == 200
        assert request(port, "GET", "/animals?_rsc=approved-page") == 200
        review_path = (
            "/v1/management/ai-observations/"
            "00000000-0000-4000-8000-000000000000/review?unexpected=1"
        )
        count = sum(ProbeHandler.counts.values())
        assert request(port, "POST", review_path) == 404
        assert sum(ProbeHandler.counts.values()) == count


def test_line_only_keeps_management_closed_and_line_semantics(tmp_path: Path) -> None:
    with gateway("line-only", tmp_path) as port:
        assert request(port, "GET", "/login") == 404
        assert request(port, "POST", "/v1/auth/login") == 404
        assert request(port, "POST", "/v1/line/webhook") == 200
        assert request(port, "GET", "/v1/line/webhook") == 404
        assert request(port, "GET", "/_next/webpack-hmr") == 200


@pytest.mark.parametrize(
    "profile", ["line-only", "shared-demo-production", "shared-demo-dev"]
)
def test_line_workflow_routes_survive_every_profile(profile: str, tmp_path: Path) -> None:
    animal_id = "00000000-0000-4000-8000-000000000000"
    with gateway(profile, tmp_path) as port:
        assert request(port, "POST", "/v1/line/webhook") == 200
        assert request(port, "GET", "/volunteer-application") == 200
        assert request(port, "GET", "/animal-confirmation") == 200
        assert request(port, "POST", "/v1/qr-tokens/resolve") == 200
        assert request(port, "POST", f"/v1/animals/{animal_id}/confirm") == 200
        assert request(port, "POST", "/v1/care-report-handoffs") == 200
        assert request(port, "GET", f"/v1/public/animals/{animal_id}/photo?token=cap") == 200


def test_production_has_exact_assets_without_hmr(tmp_path: Path) -> None:
    with gateway("shared-demo-production", tmp_path) as port:
        assert request(port, "GET", "/_next/static/chunks/runtime-fixture.js") == 200
        assert request(port, "GET", "/_next/static/chunks/unlisted-fixture.js") == 404
        assert request(port, "GET", "/_next/webpack-hmr") == 404


def test_shared_host_must_match_exact_runtime_authority(tmp_path: Path) -> None:
    with gateway("shared-demo-dev", tmp_path) as port:
        assert request(port, "GET", "/login", host="attacker.example") == 404
        assert request(port, "GET", "/login", host=f"127.0.0.1:{port}") == 200
