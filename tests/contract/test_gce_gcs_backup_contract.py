from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
SCRIPTS = GCE_ROOT / "scripts"
METADATA = SCRIPTS / "backup-metadata.py"
UPLOAD = SCRIPTS / "upload-backup-gcs.sh"
DOWNLOAD = SCRIPTS / "download-backup-gcs.sh"
PREFLIGHT = SCRIPTS / "gcs-backup-preflight.sh"
DOC = ROOT / "docs" / "deployment" / "gcs-backup.md"

FAKE_GCLOUD = r"""
#!/usr/bin/env python3
import json
import os
import shutil
import sys
from pathlib import Path

arguments = sys.argv[1:]
root = Path(os.environ["STRAYHUB_FAKE_GCS_ROOT"])
log = Path(os.environ["STRAYHUB_FAKE_GCS_LOG"])
with log.open("a", encoding="utf-8") as output:
    output.write(json.dumps(arguments) + "\n")

if arguments == ["storage", "--help"]:
    raise SystemExit(0)
if len(arguments) < 3 or arguments[0] != "storage":
    raise SystemExit(2)

operation = arguments[1]

def resolve(value: str) -> Path:
    if value.startswith("gs://"):
        relative = value.removeprefix("gs://")
        if not relative or ".." in relative.split("/"):
            raise SystemExit(3)
        return root / relative
    return Path(value)

if operation == "ls":
    raise SystemExit(0 if resolve(arguments[2]).exists() else 1)

if operation == "cp" and len(arguments) == 4:
    source = resolve(arguments[2])
    destination = resolve(arguments[3])
    if not source.is_file():
        raise SystemExit(4)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    raise SystemExit(0)

if operation == "rsync" and arguments[2] == "--recursive" and len(arguments) == 5:
    source = resolve(arguments[3])
    destination = resolve(arguments[4])
    if not source.is_dir():
        raise SystemExit(5)
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)
    raise SystemExit(0)

raise SystemExit(6)
"""


def _fake_cli(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    executable = tmp_path / "fake-gcloud"
    executable.write_text(textwrap.dedent(FAKE_GCLOUD).lstrip(), encoding="utf-8")
    executable.chmod(0o755)
    fake_root = tmp_path / "fake-gcs"
    fake_root.mkdir()
    log = tmp_path / "gcloud-commands.jsonl"
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "STRAYHUB_FAKE_GCS_ROOT": str(fake_root),
        "STRAYHUB_FAKE_GCS_LOG": str(log),
    }
    environment.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    return executable, environment


def _run(arguments: list[object], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(argument) for argument in arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _build_backup(tmp_path: Path, backup_id: str) -> Path:
    backup_dir = tmp_path / "local" / "gcp-demo" / backup_id
    postgres = backup_dir / "postgres"
    objects = backup_dir / "minio" / "objects" / "nested"
    postgres.mkdir(parents=True)
    objects.mkdir(parents=True)
    dump = postgres / "postgres.dump"
    dump.write_bytes(b"synthetic PostgreSQL custom dump stand-in")
    (objects / "probe.txt").write_bytes(b"synthetic MinIO object")
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    commands = (
        [
            METADATA,
            "postgres-metadata",
            "--backup-id",
            backup_id,
            "--timestamp",
            "2026-08-29T01:01:01Z",
            "--database",
            "strayhub_d3_verify",
            "--dump",
            dump,
            "--migration-head",
            "0037_animal_external_sources",
            "--pg-dump-version",
            "pg_dump 16 synthetic",
            "--output",
            postgres / "metadata.json",
        ],
        [
            METADATA,
            "minio-inventory",
            "--backup-id",
            backup_id,
            "--timestamp",
            "2026-08-29T01:01:02Z",
            "--bucket",
            "strayhub-private",
            "--objects-dir",
            backup_dir / "minio" / "objects",
            "--mc-version",
            "mc synthetic",
            "--output",
            backup_dir / "minio" / "inventory.json",
        ],
        [
            METADATA,
            "manifest",
            "--backup-id",
            backup_id,
            "--timestamp",
            "2026-08-29T01:01:01Z",
            "--environment",
            "gcp-demo",
            "--git-commit",
            "deadbee",
            "--backup-dir",
            backup_dir,
            "--output",
            backup_dir / "manifest.json",
        ],
    )
    for command in commands:
        subprocess.run(
            [str(argument) for argument in command],
            cwd=ROOT,
            env=environment,
            check=True,
        )
    return backup_dir


def _transport_arguments(script: Path, backup_dir: Path, fake_cli: Path) -> list[object]:
    return [
        script,
        "--backup-dir",
        backup_dir,
        "--bucket",
        "strayhub-d3-test-backups",
        "--prefix",
        "strayhub-backups",
        "--environment",
        "gcp-demo",
        "--gcloud-bin",
        fake_cli,
    ]


def test_simulated_upload_download_requires_complete_and_revalidates_manifest(
    tmp_path: Path,
) -> None:
    backup_id = "20260829T010101Z-d3contract"
    backup_dir = _build_backup(tmp_path, backup_id)
    fake_cli, environment = _fake_cli(tmp_path)

    preflight = _run(_transport_arguments(PREFLIGHT, backup_dir, fake_cli), environment)
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    upload = _run(_transport_arguments(UPLOAD, backup_dir, fake_cli), environment)
    assert upload.returncode == 0, upload.stdout + upload.stderr

    remote = (
        tmp_path
        / "fake-gcs"
        / "strayhub-d3-test-backups"
        / "strayhub-backups"
        / "gcp-demo"
        / backup_id
    )
    assert (remote / "_COMPLETE").read_text(encoding="utf-8").strip() == backup_id
    shutil.rmtree(backup_dir.parent.parent)

    destination = tmp_path / "downloaded"
    download = _run(
        [
            DOWNLOAD,
            "--backup-id",
            backup_id,
            "--destination-root",
            destination,
            "--bucket",
            "strayhub-d3-test-backups",
            "--prefix",
            "strayhub-backups",
            "--environment",
            "gcp-demo",
            "--gcloud-bin",
            fake_cli,
        ],
        environment,
    )
    assert download.returncode == 0, download.stdout + download.stderr
    restored = destination / "gcp-demo" / backup_id
    subprocess.run(
        [METADATA, "verify-manifest", "--manifest", restored / "manifest.json"],
        cwd=ROOT,
        check=True,
    )
    assert (restored / "minio" / "objects" / "nested" / "probe.txt").read_bytes() == (
        b"synthetic MinIO object"
    )
    command_log = (tmp_path / "gcloud-commands.jsonl").read_text()
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in command_log
    commands = [json.loads(line) for line in command_log.splitlines()]
    marker_upload = next(
        index
        for index, command in enumerate(commands)
        if command[:2] == ["storage", "cp"] and command[-1].endswith("/_COMPLETE")
    )
    verification_downloads = [
        index
        for index, command in enumerate(commands)
        if command[:3] == ["storage", "rsync", "--recursive"]
    ]
    assert marker_upload > verification_downloads[1]


def test_incomplete_or_corrupt_remote_backup_is_rejected(tmp_path: Path) -> None:
    backup_id = "20260829T020202Z-d3failure"
    backup_dir = _build_backup(tmp_path, backup_id)
    fake_cli, environment = _fake_cli(tmp_path)
    assert _run(_transport_arguments(UPLOAD, backup_dir, fake_cli), environment).returncode == 0
    remote = (
        tmp_path
        / "fake-gcs"
        / "strayhub-d3-test-backups"
        / "strayhub-backups"
        / "gcp-demo"
        / backup_id
    )
    marker = remote / "_COMPLETE"
    marker.unlink()
    base_download = [
        DOWNLOAD,
        "--backup-id",
        backup_id,
        "--destination-root",
        tmp_path / "incomplete",
        "--bucket",
        "strayhub-d3-test-backups",
        "--environment",
        "gcp-demo",
        "--gcloud-bin",
        fake_cli,
    ]
    incomplete = _run(base_download, environment)
    assert incomplete.returncode != 0
    assert "incomplete" in incomplete.stderr

    marker.write_text(f"{backup_id}\n", encoding="utf-8")
    (remote / "minio" / "objects" / "nested" / "probe.txt").write_bytes(b"corrupt")
    corrupt_arguments = list(base_download)
    corrupt_arguments[4] = tmp_path / "corrupt"
    corrupt = _run(corrupt_arguments, environment)
    assert corrupt.returncode != 0
    assert not (tmp_path / "corrupt" / "gcp-demo" / backup_id).exists()


def test_preflight_rejects_json_credentials_and_invalid_manifest(tmp_path: Path) -> None:
    backup_id = "20260829T030303Z-d3preflight"
    backup_dir = _build_backup(tmp_path, backup_id)
    fake_cli, environment = _fake_cli(tmp_path)
    json_environment = {**environment, "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/forbidden.json"}

    rejected_json = _run(_transport_arguments(PREFLIGHT, backup_dir, fake_cli), json_environment)
    assert rejected_json.returncode != 0
    assert "JSON paths are forbidden" in rejected_json.stderr

    (backup_dir / "postgres" / "postgres.dump").write_bytes(b"tampered")
    rejected_manifest = _run(_transport_arguments(UPLOAD, backup_dir, fake_cli), environment)
    assert rejected_manifest.returncode != 0
    assert not list((tmp_path / "fake-gcs").rglob("_COMPLETE"))


def test_upload_rejects_files_outside_the_manifest_layout(tmp_path: Path) -> None:
    backup_dir = _build_backup(tmp_path, "20260829T040404Z-d3layout")
    fake_cli, environment = _fake_cli(tmp_path)
    (backup_dir / "unexpected.txt").write_text("synthetic untracked artifact", encoding="utf-8")

    rejected = _run(_transport_arguments(UPLOAD, backup_dir, fake_cli), environment)

    assert rejected.returncode != 0
    assert "unexpected file in backup layout" in rejected.stderr
    assert not list((tmp_path / "fake-gcs").rglob("_COMPLETE"))


def test_gcs_remains_backup_only_and_minio_stays_runtime_storage() -> None:
    compose = yaml.safe_load(
        (GCE_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    )
    api_environment = compose["services"]["api"]["environment"]

    assert api_environment["MINIO_ENDPOINT"].startswith("${MINIO_ENDPOINT:")
    assert "GCS_BACKUP_BUCKET" not in api_environment
    assert "GCS_BACKUP_PREFIX" not in api_environment
    assert not any("gcs" in name.lower() for name in compose["services"])


def test_transfer_scripts_are_strict_adc_only_operator_tools() -> None:
    for script in (PREFLIGHT, UPLOAD, DOWNLOAD):
        assert script.is_file()
        assert script.stat().st_mode & 0o111
        text = script.read_text(encoding="utf-8")
        assert "set -euo pipefail" in text
        assert "gcs-backup-lib.sh" in text
        assert "GOOGLE_APPLICATION_CREDENTIALS=" not in text
        assert "HMAC" not in text

    upload = UPLOAD.read_text(encoding="utf-8")
    assert upload.index("gcs_validate_backup_directory") < upload.index(
        'storage rsync --recursive "$BACKUP_DIR"'
    )
    assert "verify-manifest" in (SCRIPTS / "gcs-backup-lib.sh").read_text(encoding="utf-8")
    assert upload.index('storage rsync --recursive "$remote_uri"') < upload.index(
        'storage cp "$marker" "$remote_uri/_COMPLETE"'
    )
    assert "--delete-unmatched-destination-objects" not in upload
    assert "storage rm" not in upload


def test_documented_bucket_iam_lifecycle_and_ownership_are_narrow() -> None:
    documentation = DOC.read_text(encoding="utf-8")
    normalized = " ".join(documentation.split())

    for phrase in (
        "uniform bucket-level access",
        "public access prevention",
        "roles/storage.objectCreator",
        "roles/storage.objectViewer",
        "specific backup bucket",
        "35-day age-based lifecycle",
        "seven daily plus four weekly",
        "Google-managed encryption",
        "managed-service-only Terraform",
        "live GCS acceptance is deferred",
        "Do not grant `roles/storage.objectAdmin`",
    ):
        assert phrase in normalized
    for forbidden in (
        "roles/editor",
        "roles/owner",
        "service-account json is canonical",
        "hmac is canonical",
    ):
        assert forbidden not in normalized.lower()
