"""Fail-closed manual authorization and publication-receipt contracts."""

from __future__ import annotations

import argparse
import json
import os
import re
from hashlib import sha256
from pathlib import Path

OPERATOR = "yawan0203"
REPOSITORY = "GAE-263/StrayHub"
RELEASE_REF = "refs/heads/release"
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
RUN_RE = re.compile(r"[1-9][0-9]*")
APPLICATION_CONFIG_KEYS = {
    "schema_version",
    "gcp_project_id",
    "workload_identity_provider",
    "artifact_publisher_service_account",
    "deployer_service_account",
    "artifact_registry",
    "production_instance",
    "production_zone",
}


class GateError(ValueError):
    """A manual release authorization or receipt is invalid."""


def validate_gate(
    *,
    operation: str,
    confirmation: str,
    actor: str,
    repository: str,
    event_name: str,
    ref: str,
    github_sha: str,
    input_sha: str,
    checkout_sha: str,
    release_sha: str,
    bundle_sha256: str | None = None,
) -> None:
    if operation not in {"publish", "deploy"}:
        raise GateError("operation is not a production write operation")
    if actor != OPERATOR or repository != REPOSITORY:
        raise GateError("operator or repository identity mismatch")
    if event_name != "workflow_dispatch" or ref != RELEASE_REF:
        raise GateError("manual release ref is invalid")
    identities = (github_sha, input_sha, checkout_sha, release_sha)
    if any(not SHA_RE.fullmatch(value) for value in identities):
        raise GateError("all release identities must be full lowercase SHAs")
    if len(set(identities)) != 1:
        raise GateError("release SHA identities do not match")
    if operation == "publish":
        expected = f"PUBLISH {input_sha}"
    else:
        if bundle_sha256 is None or not DIGEST_RE.fullmatch(bundle_sha256):
            raise GateError("deploy requires a lowercase bundle SHA-256")
        expected = f"DEPLOY PRODUCTION {input_sha} {bundle_sha256}"
    if confirmation != expected:
        raise GateError("confirmation does not exactly match the required operation")


def validate_line_gate(
    *,
    actor: str,
    repository: str,
    event_name: str,
    ref: str,
    github_sha: str,
    input_sha: str,
    checkout_sha: str,
    release_sha: str,
    confirmation: str,
    secret_version: str,
) -> None:
    if actor != OPERATOR or repository != REPOSITORY:
        raise GateError("operator or repository identity mismatch")
    if event_name != "workflow_dispatch" or ref != RELEASE_REF:
        raise GateError("LINE publication must be manually dispatched from release")
    identities = (github_sha, input_sha, checkout_sha, release_sha)
    if any(not SHA_RE.fullmatch(value) for value in identities) or len(set(identities)) != 1:
        raise GateError("LINE publication SHA identities do not match exact release HEAD")
    if not RUN_RE.fullmatch(secret_version):
        raise GateError("LINE token secret version must be a positive integer")
    if confirmation != f"PUBLISH LINE MENU {input_sha}":
        raise GateError("LINE publication confirmation mismatch")


def _load_json(path: Path) -> dict:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise GateError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError("publication receipt is unreadable") from exc
    if not isinstance(value, dict):
        raise GateError("publication receipt must be an object")
    return value


def create_publication_receipt(manifest_path: Path, output: Path, run_id: str) -> dict:
    manifest = _load_json(manifest_path)
    if not RUN_RE.fullmatch(run_id):
        raise GateError("publication run ID is invalid")
    git_sha = manifest.get("git_sha")
    bundle = manifest.get("release_bundle_sha256")
    images = manifest.get("images")
    if not isinstance(git_sha, str) or not SHA_RE.fullmatch(git_sha):
        raise GateError("manifest Git SHA is invalid")
    if not isinstance(bundle, str) or not DIGEST_RE.fullmatch(bundle):
        raise GateError("manifest bundle SHA-256 is invalid")
    if not isinstance(images, dict) or set(images) != {"api", "worker", "web"}:
        raise GateError("manifest image identity is invalid")
    receipt = {
        "schema_version": 1,
        "operation": "application-publication",
        "repository": REPOSITORY,
        "workflow": ".github/workflows/gce-release.yml",
        "run_id": run_id,
        "git_sha": git_sha,
        "release_id": manifest.get("release_id"),
        "release_bundle_sha256": bundle,
        "images": images,
        "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
        "verification": "passed",
        "deployment_performed": False,
    }
    output.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    return receipt


def validate_publication_receipt(
    receipt_path: Path,
    manifest_path: Path,
    *,
    git_sha: str,
    bundle_sha256: str,
    run_id: str,
) -> dict:
    receipt = _load_json(receipt_path)
    manifest = _load_json(manifest_path)
    expected_keys = {
        "schema_version",
        "operation",
        "repository",
        "workflow",
        "run_id",
        "git_sha",
        "release_id",
        "release_bundle_sha256",
        "images",
        "manifest_sha256",
        "verification",
        "deployment_performed",
    }
    if set(receipt) != expected_keys:
        raise GateError("publication receipt fields are invalid")
    expected = {
        "schema_version": 1,
        "operation": "application-publication",
        "repository": REPOSITORY,
        "workflow": ".github/workflows/gce-release.yml",
        "run_id": run_id,
        "git_sha": git_sha,
        "release_id": manifest.get("release_id"),
        "release_bundle_sha256": bundle_sha256,
        "images": manifest.get("images"),
        "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
        "verification": "passed",
        "deployment_performed": False,
    }
    if receipt != expected or manifest.get("git_sha") != git_sha:
        raise GateError("publication receipt does not match the requested release")
    if manifest.get("release_bundle_sha256") != bundle_sha256:
        raise GateError("release bundle digest mismatch")
    return receipt


def export_application_config(path: Path, output: Path) -> None:
    config = _load_json(path)
    if set(config) != APPLICATION_CONFIG_KEYS or config.get("schema_version") != 1:
        raise GateError("application release config fields are invalid")
    patterns = {
        "gcp_project_id": r"[a-z][a-z0-9-]{4,28}[a-z0-9]",
        "workload_identity_provider": (
            r"projects/[1-9][0-9]*/locations/global/"
            r"workloadIdentityPools/[a-z0-9-]+/providers/[a-z0-9-]+"
        ),
        "artifact_publisher_service_account": r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com",
        "deployer_service_account": r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com",
        "artifact_registry": r"[a-z0-9-]+-docker\.pkg\.dev/[a-z0-9-]+/[a-z0-9-]+",
        "production_instance": r"[a-z][a-z0-9-]{0,62}",
        "production_zone": r"[a-z]+-[a-z]+[0-9]-[a-z]",
    }
    for key, pattern in patterns.items():
        value = config.get(key)
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise GateError(f"invalid application release config field: {key}")
    names = {
        "project_id": "gcp_project_id",
        "provider": "workload_identity_provider",
        "publisher": "artifact_publisher_service_account",
        "deployer": "deployer_service_account",
        "registry": "artifact_registry",
        "instance": "production_instance",
        "zone": "production_zone",
    }
    output.write_text(
        "".join(f"{name}={config[field]}\n" for name, field in names.items()), encoding="utf-8"
    )


def _gate_from_environment(args: argparse.Namespace) -> None:
    validate_gate(
        operation=args.operation,
        confirmation=args.confirmation,
        actor=os.environ.get("GITHUB_ACTOR", ""),
        repository=os.environ.get("GITHUB_REPOSITORY", ""),
        event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
        ref=os.environ.get("GITHUB_REF", ""),
        github_sha=os.environ.get("GITHUB_SHA", ""),
        input_sha=args.git_sha,
        checkout_sha=args.checkout_sha,
        release_sha=args.release_sha,
        bundle_sha256=args.bundle_sha256,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    gate = subparsers.add_parser("gate")
    gate.add_argument("--operation", choices=("publish", "deploy"), required=True)
    gate.add_argument("--confirmation", required=True)
    gate.add_argument("--git-sha", required=True)
    gate.add_argument("--checkout-sha", required=True)
    gate.add_argument("--release-sha", required=True)
    gate.add_argument("--bundle-sha256")
    line = subparsers.add_parser("line-gate")
    line.add_argument("--confirmation", required=True)
    line.add_argument("--git-sha", required=True)
    line.add_argument("--checkout-sha", required=True)
    line.add_argument("--release-sha", required=True)
    line.add_argument("--secret-version", required=True)
    create = subparsers.add_parser("create-publication-receipt")
    create.add_argument("--manifest", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--run-id", required=True)
    validate = subparsers.add_parser("validate-publication-receipt")
    validate.add_argument("--receipt", type=Path, required=True)
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--git-sha", required=True)
    validate.add_argument("--bundle-sha256", required=True)
    validate.add_argument("--run-id", required=True)
    config = subparsers.add_parser("export-application-config")
    config.add_argument("--config", type=Path, required=True)
    config.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "gate":
            _gate_from_environment(args)
        elif args.command == "line-gate":
            validate_line_gate(
                actor=os.environ.get("GITHUB_ACTOR", ""),
                repository=os.environ.get("GITHUB_REPOSITORY", ""),
                event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
                ref=os.environ.get("GITHUB_REF", ""),
                github_sha=os.environ.get("GITHUB_SHA", ""),
                input_sha=args.git_sha,
                checkout_sha=args.checkout_sha,
                release_sha=args.release_sha,
                confirmation=args.confirmation,
                secret_version=args.secret_version,
            )
        elif args.command == "create-publication-receipt":
            create_publication_receipt(args.manifest, args.output, args.run_id)
        elif args.command == "validate-publication-receipt":
            validate_publication_receipt(
                args.receipt,
                args.manifest,
                git_sha=args.git_sha,
                bundle_sha256=args.bundle_sha256,
                run_id=args.run_id,
            )
        else:
            export_application_config(args.config, args.github_output)
    except GateError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
