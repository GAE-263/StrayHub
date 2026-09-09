from pathlib import Path

from scripts.generate_public_tunnel_config import generate_runtime_configs

FIXTURE_BUILD = Path("tests/security/fixtures/next-manifests")


def test_shared_production_nginx_is_exact_default_deny_and_path_only(tmp_path: Path) -> None:
    result = generate_runtime_configs(
        profile_name="shared-demo-production",
        output_dir=tmp_path,
        api_port=8001,
        web_port=3001,
        gateway_port=8082,
        build_dir=FIXTURE_BUILD,
        runtime_origin="https://Demo.Example.test:443",
    )
    config = result.nginx_path.read_text()

    assert "server_name demo.example.test;" in config
    assert "if ($http_host !~* ^demo\\.example\\.test(?::443)?$) { return 404; }" in config
    assert "location = /login" in config
    assert "location = /v1/auth/login" in config
    assert "location = /v1/management/reports" in config
    assert "location / { return 404; }" in config
    assert '$request_uri ~* "^/[^?]*(//|%2f|%5c|%2e|;)"' in config
    assert "location /v1/" not in config
    assert "location /v1/management/" not in config
    assert "/_next/webpack-hmr" not in config
    assert "location = /_next/static/chunks/runtime-fixture.js" in config
    log_format = config.split("log_format strayhub_public_sensitive", 1)[1].split(";", 1)[0]
    assert "$request_method $uri $status $body_bytes_sent" in log_format
    assert "rt=$request_time rid=$request_id" in log_format
    for forbidden in (
        "$request ",
        "$request_uri",
        "$args",
        "$http_referer",
        "$http_authorization",
    ):
        assert forbidden not in log_format


def test_line_only_does_not_include_management_routes(tmp_path: Path) -> None:
    result = generate_runtime_configs(
        profile_name="line-only",
        output_dir=tmp_path,
        api_port=8001,
        web_port=3001,
        gateway_port=8082,
    )
    config = result.nginx_path.read_text()
    assert "location = /v1/line/webhook" in config
    assert "location = /login" not in config
    assert "location = /v1/auth/login" not in config
    assert "location = /_next/webpack-hmr" in config


def test_explicit_loopback_validation_derives_trusted_ip_at_gateway(tmp_path: Path) -> None:
    result = generate_runtime_configs(
        profile_name="shared-demo-production",
        output_dir=tmp_path,
        api_port=8001,
        web_port=3001,
        gateway_port=8082,
        build_dir=FIXTURE_BUILD,
        runtime_origin="http://127.0.0.1:8082",
        allow_loopback_for_test=True,
    )
    config = result.nginx_path.read_text()

    assert "proxy_set_header X-StrayHub-Trusted-Client-IP $remote_addr;" in config


def test_public_gateway_only_accepts_edge_overwritten_trusted_ip(tmp_path: Path) -> None:
    result = generate_runtime_configs(
        profile_name="shared-demo-production",
        output_dir=tmp_path,
        api_port=8001,
        web_port=3001,
        gateway_port=8082,
        build_dir=FIXTURE_BUILD,
        runtime_origin="https://demo.example.test",
    )
    config = result.nginx_path.read_text()

    assert (
        "proxy_set_header X-StrayHub-Trusted-Client-IP $http_x_strayhub_trusted_client_ip;"
    ) in config
