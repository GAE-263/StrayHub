from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
SCRIPTS = GCE_ROOT / "scripts"
GENERATED = GCE_ROOT / "backup" / "generated"
DOC = ROOT / "docs" / "deployment" / "backup-restore.md"
METADATA = SCRIPTS / "backup-metadata.py"


def _script(name: str) -> str:
    path = SCRIPTS / name
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) & 0o111
    return path.read_text(encoding="utf-8")


def test_backup_artifacts_use_a_narrow_gitignored_private_staging_path() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "infra/gce/backup/generated/probe"],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 0
    assert "infra/gce/backup/generated/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "umask 077" in _script("backup-all.sh")

    broad_root = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{SCRIPTS / "backup-lib.sh"}"; backup_prepare_directory /var/tmp',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert broad_root.returncode != 0
    assert "refusing broad" in broad_root.stderr


def test_postgres_scripts_use_containerized_custom_dump_and_guarded_restore() -> None:
    backup = _script("backup-postgres.sh")
    restore = _script("restore-postgres.sh")

    assert "backup_compose exec -T postgres" in backup
    assert "pg_dump" in backup
    assert "--format=custom" in backup
    assert "--no-owner" in backup
    assert "POSTGRES_PASSWORD" not in backup
    assert "--backup-file" in restore
    assert "--confirm-isolated-restore" in restore
    assert "backup_validate_restore_database" in restore
    assert "pg_restore --list" in restore
    assert "pg_restore" in restore
    assert "restored Alembic head mismatch" in restore
    assert "runtime role safety flags changed" in restore


def test_minio_scripts_preserve_objects_and_guard_isolated_restore() -> None:
    backup = _script("backup-minio.sh")
    restore = _script("restore-minio.sh")

    assert "mc mirror --overwrite" in backup
    assert "minio-inventory" in backup
    assert "--backup-objects-dir" in restore
    assert "--confirm-isolated-restore" in restore
    assert "backup_validate_restore_bucket" in restore
    assert "mc anonymous set none" in restore
    assert "verify-minio" in restore
    for source in (backup, restore):
        assert "gcloud" not in source
        assert "gsutil" not in source


def test_manifest_helper_generates_and_verifies_required_nonsecret_metadata(tmp_path: Path) -> None:
    backup_id = "20260829T000000Z-b3contract"
    backup_dir = tmp_path / backup_id
    postgres = backup_dir / "postgres"
    objects = backup_dir / "minio" / "objects" / "nested"
    postgres.mkdir(parents=True)
    objects.mkdir(parents=True)
    dump = postgres / "postgres.dump"
    dump.write_bytes(b"synthetic custom-format stand-in")
    (objects / "probe.txt").write_bytes(b"synthetic object bytes")
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    subprocess.run(
        [
            METADATA,
            "postgres-metadata",
            "--backup-id",
            backup_id,
            "--timestamp",
            "2026-08-29T00:00:00Z",
            "--database",
            "strayhub_b3_verify",
            "--dump",
            dump,
            "--migration-head",
            "0037_animal_external_sources",
            "--pg-dump-version",
            "pg_dump 16",
            "--output",
            postgres / "metadata.json",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    subprocess.run(
        [
            METADATA,
            "minio-inventory",
            "--backup-id",
            backup_id,
            "--timestamp",
            "2026-08-29T00:00:01Z",
            "--bucket",
            "strayhub-private",
            "--objects-dir",
            backup_dir / "minio" / "objects",
            "--mc-version",
            "mc test",
            "--output",
            backup_dir / "minio" / "inventory.json",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    manifest = backup_dir / "manifest.json"
    subprocess.run(
        [
            METADATA,
            "manifest",
            "--backup-id",
            backup_id,
            "--timestamp",
            "2026-08-29T00:00:00Z",
            "--environment",
            "gcp-demo",
            "--git-commit",
            "deadbee",
            "--backup-dir",
            backup_dir,
            "--output",
            manifest,
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    subprocess.run(
        [METADATA, "verify-manifest", "--manifest", manifest],
        cwd=ROOT,
        env=environment,
        check=True,
    )

    value = json.loads(manifest.read_text(encoding="utf-8"))
    assert value["backup_id"] == backup_id
    assert value["postgres"]["migration_head"] == "0037_animal_external_sources"
    assert value["minio"]["object_count"] == 1
    assert value["consistency"]["transactionally_atomic"] is False
    normalized = json.dumps(value).lower()
    for forbidden in ("password", "secret", "token", "private_key", "access_key"):
        assert forbidden not in normalized

    inventory_path = backup_dir / "minio" / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["inventory_sha256"] = "0" * 64
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    tampered = subprocess.run(
        [METADATA, "verify-manifest", "--manifest", manifest],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tampered.returncode != 0


def test_backup_tools_add_no_service_port_or_nginx_route() -> None:
    compose = yaml.safe_load(
        (GCE_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    )
    published = {name for name, service in compose["services"].items() if service.get("ports")}
    nginx = (GCE_ROOT / "nginx" / "strayhub.conf").read_text(encoding="utf-8").lower()

    assert published == {"nginx"}
    assert not any("backup" in name or "restore" in name for name in compose["services"])
    assert "backup" not in nginx
    assert "minio" not in nginx
    assert "postgres" not in nginx


def test_documentation_states_local_limit_retention_and_gcs_deferral() -> None:
    documentation = DOC.read_text(encoding="utf-8")
    normalized = " ".join(documentation.split())

    for phrase in (
        "not an off-VM or durable production backup",
        "35-day age-based lifecycle",
        "seven-daily/four-weekly selection",
        "transactionally_atomic: false",
        "writes `_COMPLETE` last",
        "live bucket/IAM/lifecycle and restore acceptance remain required",
        "Only names beginning `strayhub_b3_restore_`",
        "Only bucket names beginning `strayhub-b3-restore-`",
    ):
        assert phrase in normalized


def test_scripts_have_no_cloud_run_cloud_sql_or_live_gcs_dependency() -> None:
    b3_scripts = (
        "backup-all.sh",
        "backup-postgres.sh",
        "backup-minio.sh",
        "restore-postgres.sh",
        "restore-minio.sh",
    )
    combined = "\n".join(_script(name) for name in b3_scripts)
    normalized = combined.lower()

    for forbidden in ("cloud run", "cloud sql", "gs://", "gcloud", "gsutil"):
        assert forbidden not in normalized
