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


def test_management_wrapper_requires_explicit_profile() -> None:
    source = Path("scripts/demo-management.sh").read_text()
    assert "--profile shared-demo-production" in source
    assert "--profile shared-demo-dev" in source
    assert 'exec "$ROOT_DIR/scripts/demo-line.sh"' in source


def test_local_line_helper_keeps_line_only_default() -> None:
    source = Path("scripts/test_line_local.sh").read_text()
    assert 'PUBLIC_TUNNEL_PROFILE="line-only"' in source
    assert "generate_public_tunnel_config.py" in source
