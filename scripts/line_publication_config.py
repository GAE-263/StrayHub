"""Strict loader for versioned, non-secret LINE publication configuration."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

PROJECT = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
NUMBER = re.compile(r"[1-9][0-9]{5,19}")
PROVIDER = re.compile(
    r"projects/[1-9][0-9]*/locations/global/workloadIdentityPools/[a-z0-9-]+/providers/[a-z0-9-]+"
)
SERVICE_ACCOUNT = re.compile(
    r"[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com"
)
BUCKET = re.compile(r"[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]")
SECRET = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,254}")
BOT = re.compile(r"@[A-Za-z0-9._-]+")
LOCATION = re.compile(r"[a-z]+-[a-z]+[0-9]")
EXPECTED_KEYS = {
    "schema_version",
    "gcp_project_id",
    "gcp_project_number",
    "workload_identity_provider",
    "publisher_service_account",
    "manifest_bucket",
    "line_token_secret_name",
    "bot_basic_id",
    "location",
    "manifest_retention_seconds",
}


class ConfigError(ValueError):
    """The checked-in non-secret publication configuration is invalid."""


@dataclass(frozen=True)
class PublicationConfig:
    schema_version: int
    gcp_project_id: str
    gcp_project_number: str
    workload_identity_provider: str
    publisher_service_account: str
    manifest_bucket: str
    line_token_secret_name: str
    bot_basic_id: str
    location: str
    manifest_retention_seconds: int
    sha256: str


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_config(path: Path) -> PublicationConfig:
    raw = path.read_bytes()
    try:
        document = json.loads(raw, object_pairs_hook=_unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError("publication config is not valid JSON") from exc
    if not isinstance(document, dict) or set(document) != EXPECTED_KEYS:
        raise ConfigError("publication config fields do not match the strict schema")
    checks = {
        "gcp_project_id": PROJECT,
        "gcp_project_number": NUMBER,
        "workload_identity_provider": PROVIDER,
        "publisher_service_account": SERVICE_ACCOUNT,
        "manifest_bucket": BUCKET,
        "line_token_secret_name": SECRET,
        "bot_basic_id": BOT,
        "location": LOCATION,
    }
    for field, pattern in checks.items():
        value = document[field]
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ConfigError(f"invalid {field}")
    if document["schema_version"] != 1:
        raise ConfigError("unsupported publication config schema")
    if document["manifest_retention_seconds"] != 31536000:
        raise ConfigError("manifest retention must be the reviewed one-year value")
    number = document["gcp_project_number"]
    project = document["gcp_project_id"]
    if not document["workload_identity_provider"].startswith(f"projects/{number}/"):
        raise ConfigError("provider project number mismatch")
    if not document["publisher_service_account"].endswith(f"@{project}.iam.gserviceaccount.com"):
        raise ConfigError("publisher service account project mismatch")
    return PublicationConfig(**document, sha256=sha256(raw).hexdigest())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as exc:
        parser.error(str(exc))
    values = {
        "project_id": config.gcp_project_id,
        "provider": config.workload_identity_provider,
        "publisher": config.publisher_service_account,
        "bucket": config.manifest_bucket,
        "secret_name": config.line_token_secret_name,
        "bot_basic_id": config.bot_basic_id,
        "config_sha256": config.sha256,
    }
    rendered = "".join(f"{key}={value}\n" for key, value in values.items())
    if args.github_output:
        args.github_output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
