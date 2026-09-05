from pathlib import Path


def test_line_helper_defaults_to_line_only_and_shared_is_explicit() -> None:
    source = Path("scripts/demo-line.sh").read_text()
    assert 'PUBLIC_TUNNEL_PROFILE="line-only"' in source
    assert "--profile" in source
    assert "shared-demo-production" in source
    assert "shared-demo-dev" in source
    assert "generate_public_tunnel_config.py" in source
    assert "--traffic-policy-file" in source
    assert source.index("npm --prefix apps/web run build") < source.index(
        "npm --prefix apps/web run start"
    )
    assert source.index("generate_public_tunnel_config.py") < source.index(
        "uv run python -m uvicorn"
    )
    assert "--activation-evidence" in source
    assert source.index("verify_sensitive_transport_runtime.py") < source.index(
        "npm --prefix apps/web run build"
    )


def test_shared_gateway_readiness_probe_uses_the_reserved_host() -> None:
    source = Path("scripts/demo-line.sh").read_text()
    assert "gateway_health_probe()" in source
    assert 'curl -H "Host: ${NGROK_URL#https://}"' in source
    assert "if gateway_health_probe 1" in source
    assert "gateway_health_probe 5" in source


def test_line_only_optional_arguments_work_with_macos_bash_and_nounset() -> None:
    source = Path("scripts/demo-line.sh").read_text()
    assert "gateway_health_curl_args" not in source
    assert "tunnel_inspection_args" not in source
    assert "api_reload_args" not in source


def test_shared_production_tunnel_disables_ngrok_http_inspection() -> None:
    source = Path("scripts/demo-line.sh").read_text()
    assert (
        'if [[ "$PUBLIC_TUNNEL_PROFILE" == "shared-demo-production" '
        '|| "$developer_mode" == "1" ]]' in source
    )
    assert "--inspect=false" in source


def test_one_command_shared_demo_keeps_explicit_operator_authorization() -> None:
    source = Path("scripts/demo-shared-management.sh").read_text()
    assert '"$ROOT_DIR/scripts/demo.sh" check' in source
    assert '"$confirmation" == "ACTIVATE"' in source
    assert '"evidence_kind": "manual_external"' in source
    assert '"$ROOT_DIR/scripts/demo-management.sh"' in source
    assert "--profile shared-demo-production" in source
    assert 'rm -f "$EVIDENCE_FILE"' in source
    assert "password=" not in source.lower()


def test_management_wrapper_requires_explicit_profile() -> None:
    source = Path("scripts/demo-management.sh").read_text()
    assert "--profile shared-demo-production" in source
    assert "--profile shared-demo-dev" in source
    assert "--activation-evidence" in source
    assert 'exec "$ROOT_DIR/scripts/demo-line.sh"' in source


def test_local_line_helper_keeps_line_only_default() -> None:
    source = Path("scripts/test_line_local.sh").read_text()
    assert 'PUBLIC_TUNNEL_PROFILE="line-only"' in source
    assert "generate_public_tunnel_config.py" in source
