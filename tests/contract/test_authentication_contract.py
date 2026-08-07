from pathlib import Path

import yaml


def test_authentication_contract_declares_all_session_operations() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    paths = document["paths"]

    assert "/v1/auth/login" in paths
    assert "/v1/auth/refresh" in paths
    assert "/v1/auth/logout" in paths
    assert "/v1/auth/me" in paths
    assert "/v1/auth/liff/exchange" in paths
    assert "/v1/auth/active-shelter-context" in paths
    assert paths["/v1/auth/login"]["post"]["security"] == []
    assert paths["/v1/auth/active-shelter-context"]["put"].get("security") is None


def test_authentication_contract_does_not_put_organization_or_role_in_token_schema() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text(encoding="utf-8")
    )
    description = document["components"]["securitySchemes"]["bearerAuth"]["description"]

    assert "Server-side Session" in description
    assert "Organization Scope" in description
