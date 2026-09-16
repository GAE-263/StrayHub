#!/usr/bin/env python3
"""Create and verify non-secret immutable GCE release artifacts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*[a-z0-9]$")
RELEASE_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
REVISION_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
COMPATIBILITY_VALUES = {
    "unknown",
    "forward-only",
    "backward-compatible-with-previous",
}
REQUIRED_IMAGES = ("api", "worker", "web")
FORBIDDEN_KEY_PARTS = ("password", "secret", "token", "private_key", "credential")
ALLOWED_ENV_FILE = "image-digests.env"
ALLOWED_NONSECRET_ENV_TEMPLATES = {"infra/gce/.env.acceptance.template"}


class ReleaseError(ValueError):
    """A fail-closed release artifact validation error."""


def validate_predecessor_identity(value: dict) -> None:
    if not isinstance(value, dict) or set(value) != {
        "git_sha",
        "release_id",
        "manifest_sha256",
        "migration_revision",
    }:
        raise ReleaseError("invalid rollback predecessor fields")
    if (
        not GIT_SHA_RE.fullmatch(str(value["git_sha"]))
        or not RELEASE_ID_RE.fullmatch(str(value["release_id"]))
        or not value["release_id"].endswith(value["git_sha"][:12])
    ):
        raise ReleaseError("invalid rollback predecessor identity")
    if not re.fullmatch(
        r"[0-9a-f]{64}", str(value["manifest_sha256"])
    ) or not REVISION_RE.fullmatch(str(value["migration_revision"])):
        raise ReleaseError("invalid rollback predecessor checksum/revision")


def reviewed_predecessor(path: Path, source: Path, revision: str) -> dict:
    review = json.loads(path.read_text())
    fields = {"schema_version", "mode", "reason", "previous"}
    if review.get("schema_version") == 2:
        fields.add("reviewed_ci_blobs")
    if set(review) != fields or (
        review["schema_version"] not in {1, 2}
        or review["mode"] != "unchanged-runtime"
        or not review["reason"]
    ):
        raise ReleaseError("unsupported compatibility review")
    previous = review["previous"]
    validate_predecessor_identity(previous)
    if previous["migration_revision"] != revision:
        raise ReleaseError("compatibility review migration mismatch")
    # CI-only exceptions are reviewed by exact blob, never by a directory wildcard.
    ci_blobs = review.get("reviewed_ci_blobs", {})
    ci_paths = {
        ".github/workflows/ci.yml",
        ".github/workflows/gce-release.yml",
        "scripts/main_ci_gate.py",
    }
    if (
        not isinstance(ci_blobs, dict)
        or not set(ci_blobs) <= ci_paths
        or any(
            not isinstance(blob, str) or not GIT_SHA_RE.fullmatch(blob)
            for blob in ci_blobs.values()
        )
    ):
        raise ReleaseError("invalid reviewed CI blobs")
    allowed = {
        "infra/gce/release-compatibility.json",
        "infra/gce/scripts/deploy-release.sh",
        "infra/gce/scripts/deployment-state.py",
        "infra/gce/scripts/release-manifest.py",
        "infra/gce/scripts/rollback-release.sh",
        "infra/gce/scripts/rollforward-release.sh",
        "scripts/build-immutable-release.sh",
        "scripts/build-release-bundle.sh",
    }

    # Compare tracked blob identities, not only Alembic revision or a caller-provided boolean.
    def runtime_tree(ref: str) -> list[bytes]:
        result = subprocess.run(
            ["git", "-C", str(source), "ls-tree", "-r", "-z", ref],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise ReleaseError("review predecessor Git tree is unavailable")
        entries = []
        seen_ci = set()
        for entry in result.stdout.split(b"\0"):
            if not entry:
                continue
            name = entry.split(b"\t", 1)[1].decode()
            if name in ci_blobs:
                if (
                    ref == "HEAD"
                    and entry.split(b"\t", 1)[0] != ("100644 blob " + ci_blobs[name]).encode()
                ):
                    raise ReleaseError("reviewed CI blob changed")
                seen_ci.add(name)
                continue
            if name not in allowed and not name.startswith(("docs/", "tests/")):
                entries.append(entry)
        if ref == "HEAD" and seen_ci != set(ci_blobs):
            raise ReleaseError("reviewed CI file missing")
        return entries

    if runtime_tree(previous["git_sha"]) != runtime_tree("HEAD"):
        raise ReleaseError("runtime changed: renew or remove the compatibility review")
    return previous


def validate_predecessor(candidate_path: Path, previous_path: Path) -> None:
    candidate = load_manifest(candidate_path)
    binding = candidate.get("rollback_predecessor")
    if binding is None:
        return  # Historical manifests retain their old unknown/forward-only behavior.
    previous = load_manifest(previous_path)
    if any(
        previous[key] != binding[key] for key in ("git_sha", "release_id", "migration_revision")
    ) or (sha256_file(previous_path) != binding["manifest_sha256"]):
        raise ReleaseError("exact rollback predecessor mismatch")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_image_reference(value: str) -> tuple[str, str]:
    if value.count("@") != 1:
        raise ReleaseError("image reference must be repository@sha256:digest")
    repository, digest = value.split("@", 1)
    if not REPOSITORY_RE.fullmatch(repository):
        raise ReleaseError(f"invalid or mutable image repository: {repository!r}")
    if not DIGEST_RE.fullmatch(digest):
        raise ReleaseError(f"invalid image digest for {repository!r}")
    return repository, digest


def validate_created_at(value: str) -> None:
    if not value.endswith("Z"):
        raise ReleaseError("created_at must be UTC and end in Z")
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ReleaseError("created_at must be RFC3339 UTC") from exc


def _literal_assignment(tree: ast.Module, name: str, path: Path) -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except (ValueError, TypeError) as exc:
                        raise ReleaseError(f"{path}: {name} must be a literal") from exc
    raise ReleaseError(f"{path}: missing {name}")


def migration_head(source_root: Path) -> str:
    versions = source_root / "services/api/migrations/versions"
    if not versions.is_dir():
        raise ReleaseError(f"missing Alembic versions directory: {versions}")
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in sorted(versions.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _literal_assignment(tree, "revision", path)
        down_revision = _literal_assignment(tree, "down_revision", path)
        if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
            raise ReleaseError(f"{path}: invalid revision")
        if revision in revisions:
            raise ReleaseError(f"duplicate Alembic revision: {revision}")
        revisions.add(revision)
        if isinstance(down_revision, str):
            parents.add(down_revision)
        elif isinstance(down_revision, (tuple, list)):
            if not all(isinstance(item, str) for item in down_revision):
                raise ReleaseError(f"{path}: invalid down_revision")
            parents.update(down_revision)
        elif down_revision is not None:
            raise ReleaseError(f"{path}: invalid down_revision")
    heads = revisions - parents
    if len(heads) != 1:
        raise ReleaseError(f"expected exactly one Alembic head, found {sorted(heads)}")
    return heads.pop()


def _safe_payload_files(payload_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(payload_dir.rglob("*")):
        relative = path.relative_to(payload_dir)
        if path.is_symlink():
            raise ReleaseError(f"release payload may not contain symlinks: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ReleaseError(f"release payload contains unsupported entry: {relative}")
        lowered = relative.name.lower()
        relative_name = relative.as_posix()
        if lowered.endswith((".pem", ".key", ".tfstate", ".tfplan")):
            raise ReleaseError(f"sensitive/generated file forbidden in release: {relative}")
        allowed_environment_file = (
            lowered == ALLOWED_ENV_FILE or relative_name in ALLOWED_NONSECRET_ENV_TEMPLATES
        )
        if (lowered.startswith(".env") or lowered.endswith(".env")) and not (
            allowed_environment_file
        ):
            raise ReleaseError(f"environment file forbidden in release: {relative}")
        files.append(path)
    if not files:
        raise ReleaseError("release payload is empty")
    return files


def create_bundle(payload_dir: Path, output: Path) -> None:
    files = _safe_payload_files(payload_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w") as archive:
        for path in files:
            relative = path.relative_to(payload_dir).as_posix()
            info = archive.gettarinfo(str(path), arcname=relative)
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = 0
            with path.open("rb") as source:
                archive.addfile(info, source)


def _safe_tar_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not member.isfile():
            raise ReleaseError(f"unsafe release bundle entry: {member.name}")
        if member.issym() or member.islnk():
            raise ReleaseError(f"release bundle links are forbidden: {member.name}")
    return members


def _read_tar_file(archive: tarfile.TarFile, name: str) -> bytes:
    try:
        member = archive.getmember(name)
    except KeyError as exc:
        raise ReleaseError(f"release bundle missing {name}") from exc
    source = archive.extractfile(member)
    if source is None:
        raise ReleaseError(f"release bundle entry is not a file: {name}")
    return source.read()


def _reject_forbidden_manifest_keys(value: Any, prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in FORBIDDEN_KEY_PARTS):
                raise ReleaseError(f"forbidden manifest key: {prefix}{key}")
            _reject_forbidden_manifest_keys(child, f"{prefix}{key}.")
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_manifest_keys(child, prefix)


def validate_manifest(data: dict[str, Any]) -> None:
    _reject_forbidden_manifest_keys(data)
    required = {
        "release_id",
        "git_sha",
        "created_at",
        "images",
        "migration_revision",
        "schema_compatibility",
        "compose_sha256",
        "release_bundle_sha256",
        "ci",
    }
    missing = required - data.keys()
    if missing:
        raise ReleaseError(f"manifest missing fields: {', '.join(sorted(missing))}")
    if not RELEASE_ID_RE.fullmatch(str(data["release_id"])):
        raise ReleaseError("invalid release_id")
    if not GIT_SHA_RE.fullmatch(str(data["git_sha"])):
        raise ReleaseError("invalid git_sha")
    if not str(data["release_id"]).endswith(str(data["git_sha"])[:12]):
        raise ReleaseError("release_id does not match git_sha")
    validate_created_at(str(data["created_at"]))
    images = data["images"]
    if not isinstance(images, dict) or set(images) != set(REQUIRED_IMAGES):
        raise ReleaseError("manifest images must contain exactly api, worker, and web")
    for service in REQUIRED_IMAGES:
        entry = images[service]
        if not isinstance(entry, dict) or set(entry) != {"repository", "digest"}:
            raise ReleaseError(f"invalid {service} image entry")
        parse_image_reference(f"{entry['repository']}@{entry['digest']}")
    if not REVISION_RE.fullmatch(str(data["migration_revision"])):
        raise ReleaseError("invalid migration_revision")
    if data["schema_compatibility"] not in COMPATIBILITY_VALUES:
        raise ReleaseError("invalid schema_compatibility")
    if "rollback_predecessor" in data:
        validate_predecessor_identity(data["rollback_predecessor"])
        if data["schema_compatibility"] != "backward-compatible-with-previous" or (
            data["migration_revision"] != data["rollback_predecessor"]["migration_revision"]
        ):
            raise ReleaseError("rollback binding incompatible with manifest")
    for field in ("compose_sha256", "release_bundle_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(data[field])):
            raise ReleaseError(f"invalid {field}")
    ci = data["ci"]
    if not isinstance(ci, dict) or set(ci) != {"provider", "run_id", "workflow"}:
        raise ReleaseError("invalid ci provenance")
    if ci["provider"] != "github-actions":
        raise ReleaseError("unsupported ci provider")
    if not all(isinstance(ci[field], str) and ci[field] for field in ("run_id", "workflow")):
        raise ReleaseError("ci provenance values must be non-empty strings")


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"unable to parse manifest: {path}") from exc
    if not isinstance(data, dict):
        raise ReleaseError("release manifest must be a JSON object")
    validate_manifest(data)
    return data


def create_manifest(args: argparse.Namespace) -> None:
    images: dict[str, dict[str, str]] = {}
    for service in REQUIRED_IMAGES:
        repository, digest = parse_image_reference(getattr(args, f"{service}_image"))
        images[service] = {"repository": repository, "digest": digest}
    data = {
        "release_id": args.release_id,
        "git_sha": args.git_sha,
        "created_at": args.created_at,
        "images": images,
        "migration_revision": args.migration_revision,
        "schema_compatibility": args.schema_compatibility,
        "compose_sha256": sha256_file(args.compose),
        "release_bundle_sha256": sha256_file(args.bundle),
        "ci": {
            "provider": "github-actions",
            "run_id": args.ci_run_id,
            "workflow": args.ci_workflow,
        },
    }
    review = getattr(args, "compatibility_review", None)
    if review:
        if args.source_root is None:
            raise ReleaseError("compatibility review requires source root")
        data["rollback_predecessor"] = reviewed_predecessor(
            review, args.source_root, args.migration_revision
        )
        data["schema_compatibility"] = "backward-compatible-with-previous"
    validate_manifest(data)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def image_env(data: dict[str, Any]) -> str:
    return "".join(
        f"STRAYHUB_{service.upper()}_IMAGE="
        f"{data['images'][service]['repository']}@{data['images'][service]['digest']}\n"
        for service in REQUIRED_IMAGES
    )


def validate_artifact(artifact_dir: Path) -> dict[str, Any]:
    manifest_path = artifact_dir / "release-manifest.json"
    bundle_path = artifact_dir / "deployment-bundle.tar"
    checksums_path = artifact_dir / "checksums.sha256"
    for path in (manifest_path, bundle_path, checksums_path):
        if not path.is_file():
            raise ReleaseError(f"release artifact missing {path.name}")
    data = load_manifest(manifest_path)
    if sha256_file(bundle_path) != data["release_bundle_sha256"]:
        raise ReleaseError("release bundle checksum mismatch")
    expected_checksums = {
        "deployment-bundle.tar": sha256_file(bundle_path),
        "release-manifest.json": sha256_file(manifest_path),
    }
    parsed_checksums: dict[str, str] = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ReleaseError("invalid checksums.sha256")
        parsed_checksums[parts[1]] = parts[0]
    if parsed_checksums != expected_checksums:
        raise ReleaseError("artifact checksums mismatch")
    with tarfile.open(bundle_path, "r") as archive:
        _safe_tar_members(archive)
        compose = _read_tar_file(archive, "infra/gce/docker-compose.production.yml")
        revision = _read_tar_file(archive, "revision").decode().strip()
        digests = _read_tar_file(archive, ALLOWED_ENV_FILE).decode()
    if hashlib.sha256(compose).hexdigest() != data["compose_sha256"]:
        raise ReleaseError("Compose checksum mismatch")
    if revision != data["git_sha"]:
        raise ReleaseError("revision does not match manifest")
    if digests != image_env(data):
        raise ReleaseError("image-digests.env does not match manifest")
    return data


def validate_release_dir(release_dir: Path) -> dict[str, Any]:
    data = load_manifest(release_dir / "release-manifest.json")
    compose = release_dir / "infra/gce/docker-compose.production.yml"
    revision = release_dir / "revision"
    digests = release_dir / ALLOWED_ENV_FILE
    for path in (compose, revision, digests):
        if not path.is_file():
            raise ReleaseError(f"release directory missing {path.relative_to(release_dir)}")
    if sha256_file(compose) != data["compose_sha256"]:
        raise ReleaseError("release Compose checksum mismatch")
    if revision.read_text(encoding="utf-8").strip() != data["git_sha"]:
        raise ReleaseError("release revision mismatch")
    if digests.read_text(encoding="utf-8") != image_env(data):
        raise ReleaseError("release image references do not match manifest")
    return data


def write_checksums(artifact_dir: Path) -> None:
    paths = (artifact_dir / "deployment-bundle.tar", artifact_dir / "release-manifest.json")
    if not all(path.is_file() for path in paths):
        raise ReleaseError("cannot write checksums before bundle and manifest exist")
    content = "".join(f"{sha256_file(path)}  {path.name}\n" for path in paths)
    (artifact_dir / "checksums.sha256").write_text(content, encoding="utf-8")


def extract_artifact(artifact_dir: Path, destination: Path) -> None:
    data = validate_artifact(artifact_dir)
    if destination.exists():
        raise ReleaseError(f"release destination already exists: {destination}")
    destination.mkdir(parents=True, mode=0o755)
    try:
        with tarfile.open(artifact_dir / "deployment-bundle.tar", "r") as archive:
            members = _safe_tar_members(archive)
            archive.extractall(destination, members=members, filter="data")
        shutil.copy2(artifact_dir / "release-manifest.json", destination)
        shutil.copy2(artifact_dir / "checksums.sha256", destination)
        if (destination / "revision").read_text(encoding="utf-8").strip() != data["git_sha"]:
            raise ReleaseError("extracted revision mismatch")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def write_receipt(args: argparse.Namespace) -> None:
    data = load_manifest(args.manifest)
    validate_created_at(args.deployed_at)
    if args.previous_release and not RELEASE_ID_RE.fullmatch(args.previous_release):
        raise ReleaseError("invalid previous release ID")
    if not args.actor or any(character in args.actor for character in "\r\n"):
        raise ReleaseError("invalid deployment actor")
    receipt = {
        "release_id": data["release_id"],
        "git_sha": data["git_sha"],
        "images": data["images"],
        "migration_revision": data["migration_revision"],
        "previous_release_id": args.previous_release or None,
        "deployed_at": args.deployed_at,
        "deployed_by_role": args.actor,
        "ci": data["ci"],
        "verification": "passed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{args.output.name}.", dir=args.output.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic create-only publication: never overwrite earlier evidence, even a symlink.
        os.link(temporary, args.output)
        parent = os.open(args.output.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        os.unlink(temporary)


def validate_receipt(manifest_path: Path, receipt_path: Path, previous: str | None = None) -> None:
    manifest = load_manifest(manifest_path)
    receipt = load_receipt(receipt_path)
    for field in ("release_id", "git_sha", "images", "migration_revision"):
        if receipt.get(field) != manifest[field]:
            raise ReleaseError(f"receipt/manifest mismatch: {field}")
    if previous is not None and receipt["previous_release_id"] != (previous or None):
        raise ReleaseError("receipt previous release mismatch")


def load_receipt(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"unable to parse deployment receipt: {path}") from exc
    if not isinstance(data, dict):
        raise ReleaseError("deployment receipt must be a JSON object")
    for field in ("release_id", "previous_release_id", "verification"):
        if field not in data:
            raise ReleaseError(f"deployment receipt missing {field}")
    if not RELEASE_ID_RE.fullmatch(str(data["release_id"])):
        raise ReleaseError("invalid receipt release_id")
    previous = data["previous_release_id"]
    if previous is not None and not RELEASE_ID_RE.fullmatch(str(previous)):
        raise ReleaseError("invalid receipt previous_release_id")
    if data["verification"] != "passed":
        raise ReleaseError("current deployment receipt is not successful")
    return data


def validate_rollback(current_manifest: Path, target_release: str, receipt_path: Path) -> None:
    current = load_manifest(current_manifest)
    receipt = load_receipt(receipt_path)
    if not RELEASE_ID_RE.fullmatch(target_release):
        raise ReleaseError("invalid rollback target release ID")
    if receipt["release_id"] != current["release_id"]:
        raise ReleaseError("current receipt and manifest disagree")
    if receipt["previous_release_id"] != target_release:
        raise ReleaseError("rollback target is not the recorded N-1 release")
    compatibility = current["schema_compatibility"]
    if compatibility != "backward-compatible-with-previous":
        raise ReleaseError(f"rollback refused: schema compatibility is {compatibility}")


def validate_rollforward(current_manifest: Path, target_manifest: Path, receipt_path: Path) -> None:
    current = load_manifest(current_manifest)
    target = load_manifest(target_manifest)
    receipt = load_receipt(receipt_path)
    if receipt["release_id"] != current["release_id"]:
        raise ReleaseError("current receipt and manifest disagree")
    if receipt["previous_release_id"] != target["release_id"]:
        raise ReleaseError("roll-forward target is not the recorded previous release")
    if target["created_at"] <= current["created_at"]:
        raise ReleaseError("roll-forward target is not newer than current release")
    if target["migration_revision"] != current["migration_revision"]:
        raise ReleaseError("roll-forward requires the same migration revision")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    head = subparsers.add_parser("migration-head")
    head.add_argument("--source-root", type=Path, required=True)

    bundle = subparsers.add_parser("create-bundle")
    bundle.add_argument("--payload-dir", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)

    create = subparsers.add_parser("create-manifest")
    create.add_argument("--compatibility-review", type=Path)
    create.add_argument("--source-root", type=Path)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--release-id", required=True)
    create.add_argument("--git-sha", required=True)
    create.add_argument("--created-at", required=True)
    for service in REQUIRED_IMAGES:
        create.add_argument(f"--{service}-image", required=True)
    create.add_argument("--migration-revision", required=True)
    create.add_argument(
        "--schema-compatibility", choices=sorted(COMPATIBILITY_VALUES), default="unknown"
    )
    create.add_argument("--compose", type=Path, required=True)
    create.add_argument("--bundle", type=Path, required=True)
    create.add_argument("--ci-run-id", required=True)
    create.add_argument("--ci-workflow", required=True)

    validate = subparsers.add_parser("validate-artifact")
    validate.add_argument("--artifact-dir", type=Path, required=True)

    release = subparsers.add_parser("validate-release-dir")
    release.add_argument("--release-dir", type=Path, required=True)

    checksums = subparsers.add_parser("write-checksums")
    checksums.add_argument("--artifact-dir", type=Path, required=True)

    extract = subparsers.add_parser("extract-artifact")
    extract.add_argument("--artifact-dir", type=Path, required=True)
    extract.add_argument("--destination", type=Path, required=True)

    field = subparsers.add_parser("show-field")
    field.add_argument("--manifest", type=Path, required=True)
    field.add_argument(
        "--field",
        choices=("release_id", "git_sha", "migration_revision", "schema_compatibility"),
        required=True,
    )

    receipt = subparsers.add_parser("write-receipt")
    receipt.add_argument("--manifest", type=Path, required=True)
    receipt.add_argument("--previous-release", default="")
    receipt.add_argument("--deployed-at", required=True)
    receipt.add_argument("--actor", required=True)
    receipt.add_argument("--output", type=Path, required=True)

    receipt_field = subparsers.add_parser("show-receipt-field")
    receipt_field.add_argument("--receipt", type=Path, required=True)
    receipt_field.add_argument(
        "--field", choices=("release_id", "previous_release_id"), required=True
    )
    check_receipt = subparsers.add_parser("validate-receipt")
    check_receipt.add_argument("--manifest", type=Path, required=True)
    check_receipt.add_argument("--receipt", type=Path, required=True)
    check_receipt.add_argument("--previous-release", default=None)

    rollback = subparsers.add_parser("validate-rollback")
    rollback.add_argument("--current-manifest", type=Path, required=True)
    rollback.add_argument("--target-release", required=True)
    rollback.add_argument("--receipt", type=Path, required=True)
    rollback.add_argument("--target-manifest", type=Path)
    predecessor = subparsers.add_parser("validate-predecessor")
    predecessor.add_argument("--manifest", type=Path, required=True)
    predecessor.add_argument("--previous-manifest", type=Path, required=True)

    rollforward = subparsers.add_parser("validate-rollforward")
    rollforward.add_argument("--current-manifest", type=Path, required=True)
    rollforward.add_argument("--target-manifest", type=Path, required=True)
    rollforward.add_argument("--receipt", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "migration-head":
            print(migration_head(args.source_root))
        elif args.command == "create-bundle":
            create_bundle(args.payload_dir, args.output)
        elif args.command == "create-manifest":
            create_manifest(args)
        elif args.command == "validate-artifact":
            data = validate_artifact(args.artifact_dir)
            print(f"release artifact valid: {data['release_id']}")
        elif args.command == "validate-release-dir":
            data = validate_release_dir(args.release_dir)
            print(f"release directory valid: {data['release_id']}")
        elif args.command == "write-checksums":
            write_checksums(args.artifact_dir)
        elif args.command == "extract-artifact":
            extract_artifact(args.artifact_dir, args.destination)
        elif args.command == "show-field":
            print(load_manifest(args.manifest)[args.field])
        elif args.command == "write-receipt":
            write_receipt(args)
        elif args.command == "validate-receipt":
            validate_receipt(args.manifest, args.receipt, args.previous_release)
        elif args.command == "show-receipt-field":
            value = load_receipt(args.receipt)[args.field]
            print("" if value is None else value)
        elif args.command == "validate-rollback":
            validate_rollback(args.current_manifest, args.target_release, args.receipt)
            if load_manifest(args.current_manifest).get("rollback_predecessor"):
                if args.target_manifest is None:
                    raise ReleaseError("bound rollback requires target manifest")
                validate_predecessor(args.current_manifest, args.target_manifest)
            print(f"rollback compatibility valid: {args.target_release}")
        elif args.command == "validate-predecessor":
            validate_predecessor(args.manifest, args.previous_manifest)
        elif args.command == "validate-rollforward":
            validate_rollforward(args.current_manifest, args.target_manifest, args.receipt)
            target = load_manifest(args.target_manifest)
            print(f"roll-forward compatibility valid: {target['release_id']}")
        else:  # pragma: no cover
            raise ReleaseError("unsupported command")
    except (OSError, ReleaseError, tarfile.TarError) as exc:
        print(f"release manifest error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
