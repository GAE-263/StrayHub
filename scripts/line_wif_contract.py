"""Offline validator for the future dedicated LINE publisher identity contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED = {
    "schema_version": 1,
    "repository": "GAE-263/StrayHub",
    "actor": "yawan0203",
    "event": "workflow_dispatch",
    "ref": "refs/heads/release",
    "workflow": "GAE-263/StrayHub/.github/workflows/line-rich-menu-publish.yml@refs/heads/release",
    "service_account": (
        "strayhub-line-menu-publisher@canvas-primacy-502703-k1.iam.gserviceaccount.com"
    ),
    "secret": "projects/canvas-primacy-502703-k1/secrets/strayhub-prod-line-channel-access-token",
    "bucket": "canvas-primacy-502703-k1-strayhub-line-menu-manifests",
    "allowed_permissions": [
        "secretmanager.versions.access",
        "storage.objects.create",
        "storage.objects.get",
    ],
    "forbidden_permission_prefixes": [
        "artifactregistry.",
        "compute.",
        "iap.",
        "storage.objects.delete",
        "storage.objects.list",
        "storage.objects.update",
    ],
}


class ContractError(ValueError):
    pass


def validate(path: Path) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("WIF contract is unreadable") from exc
    if value != EXPECTED:
        raise ContractError("WIF contract exceeds or differs from the reviewed identity boundary")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate(args.contract)
    except ContractError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
