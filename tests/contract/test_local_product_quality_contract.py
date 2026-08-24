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


def test_demo_script_is_executable_and_has_local_mvp_smoke_steps() -> None:
    script = ROOT / "scripts/demo.sh"
    assert script.exists()
    assert os.access(script, os.X_OK)
    text = script.read_text(encoding="utf-8")
    assert "alembic upgrade head" in text
    assert "scripts.seed_local" in text
    assert "test_us0_shelter_isolation.py" in text
    assert "test_us1_animal_selection.py" in text
    assert "test_us2_line_bot_report.py" in text
    assert "test_us3_animal_timeline.py" in text
    assert "test_ai_failure_timeline_status.py" in text
    assert 'API_BASE_URL="${API_BASE_URL:-http://${API_HOST}:${API_PORT}}"' in text


def test_line_demo_script_exposes_only_web_and_keeps_api_local() -> None:
    script = ROOT / "scripts/demo-line.sh"
    assert script.exists()
    assert os.access(script, os.X_OK)
    text = script.read_text(encoding="utf-8")
    for required in (
        "TUNNEL_PROVIDER",
        "LIFF_ID",
        "SHELTER_ENTRY_REFERENCE",
        "API_BASE_URL",
        "cloudflared",
        "ngrok",
        "volunteer-entry?entry=",
        "trap cleanup EXIT INT TERM",
        'API_BASE_URL="http://${API_HOST}:${API_PORT}"',
        'start_tunnel "Web"',
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
    assert 'start_tunnel "API"' not in text
    assert "API tunnel:" not in text
