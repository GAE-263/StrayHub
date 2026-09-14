from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.line_publication_config import ConfigError, load_config


def valid_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "gcp_project_id": "canvas-primacy-502703-k1",
        "gcp_project_number": "629644858010",
        "workload_identity_provider": (
            "projects/629644858010/locations/global/"
            "workloadIdentityPools/github-strayhub/providers/github"
        ),
        "publisher_service_account": (
            "strayhub-line-menu-publisher@canvas-primacy-502703-k1.iam.gserviceaccount.com"
        ),
        "manifest_bucket": "canvas-primacy-502703-k1-strayhub-line-menu-manifests",
        "line_token_secret_name": "strayhub-prod-line-channel-access-token",
        "bot_basic_id": "@356imngb",
        "location": "us-central1",
        "manifest_retention_seconds": 31536000,
    }


def write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_config_is_strict_and_returns_content_hash(tmp_path: Path) -> None:
    loaded = load_config(write(tmp_path / "config.json", valid_config()))
    assert loaded.gcp_project_number == "629644858010"
    assert len(loaded.sha256) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_bucket", "gs://bucket/path"),
        ("line_token_secret_name", "projects/x/secrets/y"),
        ("line_token_secret_name", "name;command"),
        ("publisher_service_account", "not-an-email"),
        ("bot_basic_id", "356imngb"),
    ],
)
def test_config_rejects_injection_and_invalid_values(
    tmp_path: Path, field: str, value: str
) -> None:
    document = valid_config()
    document[field] = value
    with pytest.raises(ConfigError):
        load_config(write(tmp_path / "config.json", document))


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate"):
        load_config(path)
