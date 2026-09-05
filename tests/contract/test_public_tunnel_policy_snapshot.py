import json
from hashlib import sha256
from pathlib import Path

from scripts.public_tunnel_policy import CompiledProfile, compile_profile

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests/security/fixtures/next-manifests"
LINE_REGISTRY = (
    ROOT / "specs/012-sensitive-data-transport-hardening/contracts/line-tunnel-allowlist.yaml"
)


def _route_digest(profile_name: str, *, production: bool = False) -> tuple[int, str, int]:
    profile, _ = compile_profile(
        profile_name,
        build_dir=FIXTURES if production else None,
        runtime_origin=(
            "https://reserved.example.ngrok.app" if profile_name != "line-only" else None
        ),
    )
    rows = "\n".join(
        f"{route.id}|{','.join(route.methods)}|{route.path or route.path_pattern}|"
        f"{route.upstream}|{route.query_policy}|{route.logging_policy}"
        for route in profile.routes
    ).encode()
    return len(profile.routes), sha256(rows).hexdigest(), len(profile.exact_assets)


def test_phase_b_policy_snapshot_is_deterministic() -> None:
    assert sha256(LINE_REGISTRY.read_bytes()).hexdigest() == (
        "4c9d7c9de0ce6379ae29a11244dbba23d2395635d6dcc77a96b14090cc4899da"
    )
    assert _route_digest("line-only") == (
        25,
        "2f73f7d603697c85cda7abba9a53d5c20a196a1f8ed691c58a313e2b3839f71a",
        0,
    )
    assert _route_digest("shared-demo-dev") == (
        48,
        "9ab82dfe6079289fa3c3271507c66653e27254333313fda9d6a9f927366f4929",
        0,
    )
    assert _route_digest("shared-demo-production", production=True) == (
        46,
        "fc5a0cffac3032e0c33987f96159962b25b03fb418e8a619e0bac74f8a7dc7d4",
        20,
    )


def test_rsc_uses_allowlisted_page_path_and_ordinary_query_policy() -> None:
    profile, _ = compile_profile(
        "shared-demo-production",
        build_dir=FIXTURES,
        runtime_origin="https://reserved.example.ngrok.app",
    )
    page_routes = [route for route in profile.routes if route.upstream == "web"]
    assert page_routes
    assert all(route.query_policy == "preserve" for route in page_routes)
    assert not any("_rsc" in (route.path or route.path_pattern or "") for route in profile.routes)


def test_authenticated_photo_preserves_the_application_version_query() -> None:
    profile, _ = compile_profile(
        "shared-demo-production",
        build_dir=FIXTURES,
        runtime_origin="https://reserved.example.ngrok.app",
    )
    route = next(item for item in profile.routes if item.id == "management_animal_photo_api")

    assert route.query_policy == "preserve"
    assert route.logging_policy == "sensitive_path_only"


def test_same_inputs_produce_byte_stable_profile_output() -> None:
    first, _ = compile_profile(
        "shared-demo-production",
        build_dir=FIXTURES,
        runtime_origin="https://reserved.example.ngrok.app",
    )
    second, _ = compile_profile(
        "shared-demo-production",
        build_dir=FIXTURES,
        runtime_origin="https://reserved.example.ngrok.app",
    )

    def serialize(profile: CompiledProfile) -> bytes:
        return json.dumps(profile.snapshot(), sort_keys=True, separators=(",", ":")).encode()

    assert serialize(first) == serialize(second)
