import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_readme_documents_the_local_quality_and_demo_boundaries() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for required in (
        "65432",
        "scripts/demo.sh",
        "scripts/verify_local.sh",
        "AUTH_JWT_ACTIVE_PRIVATE_KEY",
        "npm --prefix packages/contracts run check",
        "local-staff-a",
        "AI 失敗",
        "GCP Demo",
    ):
        assert required in readme


def test_sensitive_transport_policy_is_a_fast_local_and_ci_gate() -> None:
    verify = (ROOT / "scripts/verify_local.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    command = "uv run python scripts/check_sensitive_transport_policy.py"

    assert command in verify
    assert verify.index(command) < verify.index('echo "[T224] Migration"')
    assert command in workflow
    assert workflow.index(command) < workflow.index("uv run alembic upgrade head")


def test_demo_script_is_executable_and_separates_demo_from_test_fixtures() -> None:
    script = ROOT / "scripts/demo.sh"
    assert script.exists()
    assert os.access(script, os.X_OK)
    text = script.read_text(encoding="utf-8")
    assert "alembic upgrade head" in text
    assert "scripts.seed_local" not in text
    assert "uv run pytest" not in text
    assert "scripts.bootstrap_demo" in text
    assert "scripts.configure_runtime_role --apply" in text
    assert 'API_BASE_URL="${API_BASE_URL:-http://${API_HOST}:${API_PORT}}"' in text


def test_demo_scripts_require_explicit_interactive_secret_reveal() -> None:
    demo = (ROOT / "scripts/demo.sh").read_text(encoding="utf-8")
    line_demo = (ROOT / "scripts/demo-line.sh").read_text(encoding="utf-8")

    assert "--reveal-demo-password" in demo
    assert "demo_password_reveal_confirmed" in demo
    assert "Generated demo password (shown once" not in demo
    assert "--reveal-entry-reference" in line_demo
    assert "entry_reference_reveal_confirmed" in line_demo
    assert 'echo "  ${LIFF_ENDPOINT_URL}"' not in line_demo


def test_line_demo_script_exposes_only_default_deny_gateway_and_keeps_upstreams_local() -> None:
    script = ROOT / "scripts/demo-line.sh"
    assert script.exists()
    assert os.access(script, os.X_OK)
    text = script.read_text(encoding="utf-8")
    for required in (
        "NGROK_URL",
        "LIFF_ID",
        "SHELTER_ENTRY_REFERENCE",
        "API_BASE_URL",
        "ngrok",
        'ngrok http "$port" --url "$NGROK_URL"',
        'start_tunnel "Gateway" "$NGINX_PORT"',
        'NGINX_TEMPLATE="infra/local/nginx/line-local.conf.template"',
        "volunteer-entry?entry=",
        "trap cleanup EXIT INT TERM",
        'API_BASE_URL="http://${API_HOST}:${API_PORT}"',
        "wait_for_tunnel_http",
        "Could not reach tunnel",
        "@1.1.1.1",
        "--resolve",
        "TUNNEL_URL=",
        "read_dotenv_value",
        "source .env" not in text,
    ):
        if isinstance(required, bool):
            assert required
        else:
            assert required in text
    assert "TUNNEL_PROVIDER" not in text
    assert "cloudflared" not in text
    assert 'start_tunnel "API"' not in text
    assert 'start_tunnel "Web" "$WEB_PORT"' not in text
    assert "API tunnel:" not in text
    assert 'LIFF_URL="https://liff.line.me/${LIFF_ID}"' in text
    assert (
        'LIFF_ENDPOINT_URL="${WEB_TUNNEL_URL}/volunteer-entry?entry=${SHELTER_ENTRY_REFERENCE}"'
        in text
    )
    assert "/${LIFF_ID}/volunteer-entry?entry=" not in text


def test_line_demo_does_not_run_test_fixtures_or_retarget_the_database() -> None:
    text = (ROOT / "scripts/demo-line.sh").read_text(encoding="utf-8")

    for forbidden in (
        "scripts.seed_local",
        "scripts.test_local",
        "scripts/test_local.py",
        "uv run pytest",
        "strayhub_test",
        "ORG-A",
    ):
        assert forbidden not in text
    assert "DATABASE_URL=" not in text


def test_line_demo_allows_the_generated_web_tunnel_dev_origin() -> None:
    script = (ROOT / "scripts/demo-line.sh").read_text(encoding="utf-8")
    next_config = (ROOT / "apps/web/next.config.ts").read_text(encoding="utf-8")

    assert "LINE_DEMO_WEB_ORIGIN_HOST" in script
    assert "LINE_DEMO_WEB_ORIGIN_HOST" in next_config
    assert script.index("npm --prefix apps/web run dev") < script.index('start_tunnel "Gateway"')


def test_line_demo_provides_session_keys_before_starting_api() -> None:
    script = (ROOT / "scripts/demo-line.sh").read_text(encoding="utf-8")

    assert "AUTH_JWT_ACTIVE_PRIVATE_KEY" in script
    assert "AUTH_JWT_ACTIVE_PUBLIC_KEY" in script
    assert "openssl genpkey" in script
    assert script.index("openssl genpkey") < script.index("uv run python -m uvicorn")


def test_line_demo_provides_public_photo_origin_before_starting_api() -> None:
    script = (ROOT / "scripts/demo-line.sh").read_text(encoding="utf-8")

    assignment = 'export WEB_PUBLIC_BASE_URL="$NGROK_URL"'
    assert assignment in script
    assert script.index(assignment) < script.index("uv run python -m uvicorn")


def test_local_demo_scripts_provide_ephemeral_pii_key_before_starting_api() -> None:
    for relative_path in ("scripts/demo.sh", "scripts/demo-line.sh"):
        script = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "PII_ALLOW_LOCAL_PROVIDER" in script
        assert "PII_LOCAL_KEY_BASE64" in script
        assert "openssl rand -base64 32" in script
        assert script.index("openssl rand -base64 32") < script.index("uv run python -m uvicorn")


def test_line_demo_requires_login_channel_for_real_liff() -> None:
    script = (ROOT / "scripts/demo-line.sh").read_text(encoding="utf-8")

    assert "LINE_LOGIN_CHANNEL_ID" in script
    assert "真實 LIFF_ID 必須搭配 LINE_LOGIN_CHANNEL_ID" in script
