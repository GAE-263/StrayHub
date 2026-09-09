from pathlib import Path

import pytest
from scripts.public_tunnel_policy import PolicyError, extract_next_public_assets

FIXTURES = Path(__file__).parents[1] / "security/fixtures/next-manifests"
ALLOWED = (
    "/login",
    "/",
    "/animals",
    "/animals/[animalId]",
    "/animals/[animalId]/timeline",
    "/reports",
    "/reports/[reportId]",
    "/ai-review",
    "/care-calendar",
    "/volunteer-entry",
    "/volunteer-application",
    "/animal-confirmation",
    "/care-report",
)


def test_extracts_only_exact_js_and_css_for_allowed_pages() -> None:
    assets = extract_next_public_assets(FIXTURES, ALLOWED)

    assert assets == tuple(sorted(assets))
    assert "/_next/static/chunks/runtime-fixture.js" in assets
    assert "/_next/static/css/shared-fixture.css" in assets
    assert "/_next/static/chunks/management-layout-fixture.js" in assets
    assert "/_next/static/chunks/volunteer-layout-fixture.js" in assets
    assert "/_next/static/chunks/onboarding-layout-fixture.js" in assets
    assert all(path.startswith("/_next/static/") for path in assets)
    assert all(path.endswith((".js", ".css")) for path in assets)
    assert not any(path.endswith(".map") for path in assets)
    assert not any("unlisted" in path for path in assets)


def test_missing_manifest_and_unresolved_page_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="manifest"):
        extract_next_public_assets(tmp_path, ALLOWED)

    with pytest.raises(PolicyError, match="unresolved page"):
        extract_next_public_assets(FIXTURES, (*ALLOWED, "/not-built"))


def test_unknown_next_internal_asset_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "build-manifest.json").write_text(
        '{"polyfillFiles":[],"rootMainFiles":["../server/secret.js"]}'
    )
    (tmp_path / "app-build-manifest.json").write_text(
        '{"pages":{"/layout":["static/chunks/layout.js"],"/page":["static/chunks/page.js"]}}'
    )
    with pytest.raises(PolicyError, match="asset"):
        extract_next_public_assets(tmp_path, ("/",))
