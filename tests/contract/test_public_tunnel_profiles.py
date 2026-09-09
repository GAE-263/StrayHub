from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from scripts.public_tunnel_policy import (
    PolicyError,
    compile_profile_documents,
    validate_management_registry,
    validate_route_conflicts,
)

ROOT = Path(__file__).parents[2]
PROFILE_PATH = (
    ROOT / "specs/013-remote-management-public-access/contracts/public-tunnel-profiles.yaml"
)


def _documents() -> tuple[dict, dict, dict]:
    profiles = yaml.safe_load(PROFILE_PATH.read_text())
    line_path = (PROFILE_PATH.parent / profiles["registries"]["line"]["path"]).resolve()
    management_path = (PROFILE_PATH.parent / profiles["registries"]["management"]["path"]).resolve()
    return (
        profiles,
        yaml.safe_load(line_path.read_text()),
        yaml.safe_load(management_path.read_text()),
    )


def test_profiles_compose_without_copying_line_routes() -> None:
    profiles, line, management = _documents()

    line_only = compile_profile_documents("line-only", profiles, line, management)
    production = compile_profile_documents(
        "shared-demo-production",
        profiles,
        line,
        management,
        exact_assets=("/_next/static/chunks/runtime-a.js",),
    )
    development = compile_profile_documents("shared-demo-dev", profiles, line, management)

    assert len(line_only.routes) == 25
    assert len(development.routes) == 48
    assert {"next_dev_hmr", "next_static_assets"}.isdisjoint(production.route_ids)
    assert production.exact_assets == ("/_next/static/chunks/runtime-a.js",)
    assert "next_dev_hmr" in development.route_ids
    assert "next_static_assets" in development.route_ids


def test_unknown_profile_registry_and_exclusion_fail_closed() -> None:
    profiles, line, management = _documents()
    with pytest.raises(PolicyError, match="unknown profile"):
        compile_profile_documents("missing", profiles, line, management)

    bad_registry = deepcopy(profiles)
    bad_registry["profiles"]["line-only"]["include_registries"] = ["missing"]
    with pytest.raises(PolicyError, match="unknown registry"):
        compile_profile_documents("line-only", bad_registry, line, management)

    bad_exclusion = deepcopy(profiles)
    bad_exclusion["profiles"]["line-only"]["exclude_route_ids"] = ["missing"]
    with pytest.raises(PolicyError, match="unknown exclusion"):
        compile_profile_documents("line-only", bad_exclusion, line, management)


def test_duplicate_ids_and_conflicting_routes_fail_closed() -> None:
    profiles, line, management = _documents()
    duplicate = deepcopy(management)
    duplicate["routes"][1]["id"] = duplicate["routes"][0]["id"]
    with pytest.raises(PolicyError, match="duplicate route id"):
        compile_profile_documents("shared-demo-dev", profiles, line, duplicate)

    conflict = deepcopy(management)
    conflict["routes"][1]["path"] = conflict["routes"][0]["path"]
    conflict["routes"][1]["upstream"] = "api"
    with pytest.raises(PolicyError, match="conflict"):
        compile_profile_documents("shared-demo-dev", profiles, line, conflict)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authentication", "none"),
        ("roles", ["ANONYMOUS"]),
        ("query_policy", "reject_nonempty"),
        ("logging_policy", "full_request_uri"),
        ("rate_limit_expectation", "gateway_baseline_only"),
    ],
)
def test_same_method_path_with_incompatible_security_policy_fails_closed(
    field: str, value: object
) -> None:
    _, _, management = _documents()
    original = validate_management_registry(management)[0]
    conflict = replace(original, id="conflicting_route", **{field: value})
    with pytest.raises(PolicyError, match="conflict"):
        validate_route_conflicts((original, conflict))


def test_duplicate_bounded_patterns_fail_closed() -> None:
    profiles, line, management = _documents()
    duplicate = deepcopy(management)
    duplicate["routes"][5]["path_pattern"] = duplicate["routes"][3]["path_pattern"]
    with pytest.raises(PolicyError, match="conflict"):
        compile_profile_documents("shared-demo-dev", profiles, line, duplicate)


def test_line_compatibility_metadata_must_cover_each_route_once() -> None:
    profiles, line, management = _documents()
    profiles = deepcopy(profiles)
    profiles["legacy_line_registry_effective_metadata"]["groups"]["signed_line_ingress"][
        "route_ids"
    ].append("volunteer_entry_page")

    with pytest.raises(PolicyError, match="compatibility metadata"):
        compile_profile_documents("line-only", profiles, line, management)


@pytest.mark.parametrize(
    "asset",
    ["/_next/**", "/_next/image", "/_next/static/chunk.js.map", "/server/secret.js"],
)
def test_production_profile_rejects_non_exact_or_unapproved_assets(asset: str) -> None:
    profiles, line, management = _documents()
    with pytest.raises(PolicyError, match="unsafe exact asset"):
        compile_profile_documents(
            "shared-demo-production", profiles, line, management, exact_assets=(asset,)
        )
