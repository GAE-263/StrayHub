from copy import deepcopy
from pathlib import Path

import pytest
import yaml

CONTRACT = (
    Path(__file__).parents[2]
    / "specs/013-remote-management-public-access/contracts/management-tunnel-allowlist.yaml"
)


def _document() -> dict:
    return yaml.safe_load(CONTRACT.read_text())


def test_management_registry_has_23_complete_bounded_routes() -> None:
    from scripts.public_tunnel_policy import validate_management_registry

    routes = validate_management_registry(_document())

    assert len(routes) == 23
    assert len({route.id for route in routes}) == 23
    assert all(route.demo_required for route in routes)
    assert all(route.category for route in routes)
    assert all(route.evidence and route.tests for route in routes)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "/v1/**"),
        ("path", "/v1/management/**"),
        ("path", "/**"),
        ("path_pattern", "^/.*$"),
        ("path_pattern", "^/_next/.*$"),
        ("path_pattern", "/animals/[0-9a-f-]+"),
    ],
)
def test_management_registry_rejects_broad_or_unanchored_routes(field: str, value: str) -> None:
    from scripts.public_tunnel_policy import PolicyError, validate_management_registry

    document = _document()
    route = document["routes"][0]
    route.pop("path", None)
    route.pop("path_pattern", None)
    route[field] = value

    with pytest.raises(PolicyError, match="management_login_page"):
        validate_management_registry(document)


@pytest.mark.parametrize(
    "path",
    [
        "/v1/platform/users",
        "/platform",
        "/v1/management/volunteers/private-profile",
    ],
)
def test_management_registry_rejects_platform_and_pii_surfaces(path: str) -> None:
    from scripts.public_tunnel_policy import PolicyError, validate_management_registry

    document = _document()
    document["routes"][0]["path"] = path

    with pytest.raises(PolicyError):
        validate_management_registry(document)


def test_management_registry_rejects_missing_metadata_without_defaults() -> None:
    from scripts.public_tunnel_policy import PolicyError, validate_management_registry

    document = deepcopy(_document())
    del document["routes"][0]["demo_required"]

    with pytest.raises(PolicyError, match="demo_required"):
        validate_management_registry(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authentication", "trust_client_header"),
        ("roles", ["PLATFORM_ADMIN"]),
        ("query_policy", "forward_everything"),
        ("logging_policy", "full_request_uri"),
        ("rate_limit_expectation", "none"),
        ("upstream", "internal-admin"),
        ("demo_required", False),
    ],
)
def test_management_registry_rejects_unknown_security_contract_values(
    field: str, value: object
) -> None:
    from scripts.public_tunnel_policy import PolicyError, validate_management_registry

    document = _document()
    document["routes"][0][field] = value
    with pytest.raises(PolicyError, match="management_login_page"):
        validate_management_registry(document)


@pytest.mark.parametrize("path", ["/animals//detail", "/animals/%2e%2e/admin", "/animals;admin"])
def test_management_registry_rejects_path_normalization_bypasses(path: str) -> None:
    from scripts.public_tunnel_policy import PolicyError, validate_management_registry

    document = _document()
    document["routes"][0]["path"] = path
    with pytest.raises(PolicyError, match="management_login_page"):
        validate_management_registry(document)
