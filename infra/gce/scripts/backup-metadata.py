#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _inventory(objects_dir: Path, bucket: str) -> dict[str, Any]:
    root = objects_dir.resolve(strict=True)
    objects: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix()):
        if path.is_symlink():
            raise ValueError(f"symlink is forbidden in backup objects: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        objects.append({"key": relative, "sha256": _sha256(path), "size": path.stat().st_size})
    canonical = json.dumps(objects, separators=(",", ":"), sort_keys=True).encode()
    return {
        "schema_version": SCHEMA_VERSION,
        "bucket": bucket,
        "object_count": len(objects),
        "objects": objects,
        "inventory_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _postgres_metadata(arguments: argparse.Namespace) -> None:
    dump = Path(arguments.dump).resolve(strict=True)
    _write_json(
        Path(arguments.output),
        {
            "schema_version": SCHEMA_VERSION,
            "backup_id": arguments.backup_id,
            "timestamp_utc": arguments.timestamp,
            "database": arguments.database,
            "artifact": "postgres/postgres.dump",
            "sha256": _sha256(dump),
            "migration_head": arguments.migration_head,
            "pg_dump_version": arguments.pg_dump_version,
            "format": "custom",
        },
    )


def _minio_inventory(arguments: argparse.Namespace) -> None:
    _write_json(
        Path(arguments.output),
        _inventory(Path(arguments.objects_dir), arguments.bucket)
        | {
            "backup_id": arguments.backup_id,
            "timestamp_utc": arguments.timestamp,
            "artifact_directory": "minio/objects",
            "mc_version": arguments.mc_version,
        },
    )


def _verify_minio(arguments: argparse.Namespace) -> None:
    expected = _load_json(Path(arguments.inventory))
    actual = _inventory(Path(arguments.objects_dir), str(expected["bucket"]))
    for key in ("object_count", "objects", "inventory_sha256"):
        if actual[key] != expected.get(key):
            raise ValueError(f"MinIO inventory mismatch: {key}")
    print(f"object_count={actual['object_count']}")
    print(f"inventory_sha256={actual['inventory_sha256']}")


def _manifest(arguments: argparse.Namespace) -> None:
    backup_dir = Path(arguments.backup_dir).resolve(strict=True)
    postgres = _load_json(backup_dir / "postgres" / "metadata.json")
    minio = _load_json(backup_dir / "minio" / "inventory.json")
    if postgres["backup_id"] != arguments.backup_id or minio["backup_id"] != arguments.backup_id:
        raise ValueError("component backup IDs do not match")
    if _sha256(backup_dir / postgres["artifact"]) != postgres["sha256"]:
        raise ValueError("PostgreSQL dump checksum mismatch")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "backup_id": arguments.backup_id,
        "timestamp_utc": arguments.timestamp,
        "environment": arguments.environment,
        "script_version": "b3-v1",
        "git_commit": arguments.git_commit,
        "consistency": {
            "transactionally_atomic": False,
            "note": "PostgreSQL and MinIO are captured sequentially under one backup ID.",
        },
        "postgres": postgres,
        "minio": minio,
    }
    _write_json(Path(arguments.output), manifest)


def _verify_manifest(arguments: argparse.Namespace) -> None:
    manifest_path = Path(arguments.manifest).resolve(strict=True)
    manifest = _load_json(manifest_path)
    backup_dir = manifest_path.parent
    required = {
        "schema_version",
        "backup_id",
        "timestamp_utc",
        "environment",
        "script_version",
        "git_commit",
        "consistency",
        "postgres",
        "minio",
    }
    if not required <= manifest.keys():
        raise ValueError("manifest is missing required fields")
    postgres = manifest["postgres"]
    postgres_metadata = _load_json(backup_dir / "postgres" / "metadata.json")
    if postgres != postgres_metadata:
        raise ValueError("manifest PostgreSQL metadata mismatch")
    if _sha256(backup_dir / postgres["artifact"]) != postgres["sha256"]:
        raise ValueError("manifest PostgreSQL checksum mismatch")
    minio_inventory = backup_dir / "minio" / "inventory.json"
    expected_minio = _load_json(minio_inventory)
    if manifest["minio"] != expected_minio:
        raise ValueError("manifest MinIO metadata mismatch")
    actual_minio = _inventory(backup_dir / "minio" / "objects", expected_minio["bucket"])
    for key in ("object_count", "objects", "inventory_sha256"):
        if actual_minio[key] != expected_minio.get(key):
            raise ValueError(f"manifest MinIO inventory mismatch: {key}")
    forbidden = {"password", "secret", "token", "private_key", "access_key"}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key.lower() in forbidden:
                    raise ValueError(f"secret-like manifest field is forbidden: {key}")
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(manifest)
    print(f"backup_id={manifest['backup_id']}")
    print(f"postgres_sha256={postgres['sha256']}")
    print(f"minio_object_count={expected_minio['object_count']}")
    print(f"minio_inventory_sha256={expected_minio['inventory_sha256']}")


def _field(arguments: argparse.Namespace) -> None:
    value: Any = _load_json(Path(arguments.input))
    for part in arguments.path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"missing metadata field: {arguments.path}")
        value = value[part]
    if isinstance(value, (dict, list)):
        raise ValueError("field command supports scalar values only")
    print(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)

    postgres = commands.add_parser("postgres-metadata")
    for option in (
        "backup-id",
        "timestamp",
        "database",
        "dump",
        "migration-head",
        "pg-dump-version",
        "output",
    ):
        postgres.add_argument(f"--{option}", required=True)
    postgres.set_defaults(handler=_postgres_metadata)

    minio = commands.add_parser("minio-inventory")
    for option in ("backup-id", "timestamp", "bucket", "objects-dir", "mc-version", "output"):
        minio.add_argument(f"--{option}", required=True)
    minio.set_defaults(handler=_minio_inventory)

    verify_minio = commands.add_parser("verify-minio")
    verify_minio.add_argument("--objects-dir", required=True)
    verify_minio.add_argument("--inventory", required=True)
    verify_minio.set_defaults(handler=_verify_minio)

    manifest = commands.add_parser("manifest")
    for option in ("backup-id", "timestamp", "environment", "git-commit", "backup-dir", "output"):
        manifest.add_argument(f"--{option}", required=True)
    manifest.set_defaults(handler=_manifest)

    verify_manifest = commands.add_parser("verify-manifest")
    verify_manifest.add_argument("--manifest", required=True)
    verify_manifest.set_defaults(handler=_verify_manifest)

    field = commands.add_parser("field")
    field.add_argument("--input", required=True)
    field.add_argument("--path", required=True)
    field.set_defaults(handler=_field)
    return parser


def main() -> None:
    os.umask(0o077)
    arguments = _parser().parse_args()
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
