from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = ROOT / "infra" / "gcp-platform" / "terraform"
LEGACY_ROOT = ROOT / "infra" / "gcp-demo"


def _read(name: str) -> str:
    return (PLATFORM_ROOT / name).read_text(encoding="utf-8")


def test_platform_root_owns_only_retained_resources() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PLATFORM_ROOT.glob("*.tf"))

    assert 'bucket = "strayhub-platform-tfstate-canvas-primacy-502703-k1"' in source
    assert 'prefix = "strayhub/platform"' in source
    assert source.count("strayhub-prod-") == 11
    assert 'resource "google_secret_manager_secret_version"' not in source
    assert 'resource "google_sql_' not in source
    assert 'resource "google_cloud_run_' not in source
    assert 'resource "google_compute_' not in source
    assert 'resource "google_project_service"' not in source
    assert "strayhub/gcp-demo" not in source


def test_retained_resources_are_fail_closed() -> None:
    secrets = _read("secrets.tf")
    kms = _read("kms.tf")
    storage = _read("storage.tf")

    assert 'role      = "roles/secretmanager.secretAccessor"' in secrets
    assert 'role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"' in kms
    assert 'role   = "roles/storage.objectCreator"' in storage
    assert 'role   = "roles/storage.objectViewer"' in storage
    assert 'public_access_prevention    = "enforced"' in storage
    assert storage.count("force_destroy               = false") == 2
    assert "retention_period = 604800" in storage
    assert "retention_duration_seconds = 604800" in storage
    assert "enabled = true" in storage
    assert (secrets + kms + storage).count("prevent_destroy = true") == 5


def test_legacy_mutation_entrypoints_fail_closed() -> None:
    forbidden = ("terraform apply", "gcloud run jobs execute", "gcloud storage rm")
    for script_name in ("apply.sh", "migrate.sh", "seed-demo.sh", "sync-line.sh"):
        script = (LEGACY_ROOT / script_name).read_text(encoding="utf-8")
        assert "exit 1" in script
        assert "retired" in script.lower()
        assert not any(command in script for command in forbidden)

    workflow = (ROOT / ".github/workflows/demo-build.yml").read_text(encoding="utf-8")
    assert "Legacy GCP Demo Validation (No Deploy)" in workflow
    assert "id-token: write" not in workflow
    assert "google-github-actions/auth" not in workflow
    assert "terraform apply" not in workflow
    assert "gcloud run" not in workflow


def test_platform_terraform_format_and_validate() -> None:
    terraform = os.environ.get("TERRAFORM_BIN") or shutil.which("terraform")
    assert terraform, "Terraform CLI is required for PLATFORM_TERRAFORM contracts"

    formatted = subprocess.run(
        [terraform, "fmt", "-check", "-recursive", str(PLATFORM_ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert formatted.returncode == 0, formatted.stdout + formatted.stderr

    # Isolate backend metadata so a developer's real initialized GCS backend is never consulted.
    with tempfile.TemporaryDirectory(prefix="strayhub-platform-tfdata-") as tf_data_dir:
        terraform_env = os.environ | {"TF_DATA_DIR": tf_data_dir}
        initialized = subprocess.run(
            [terraform, "-chdir=" + str(PLATFORM_ROOT), "init", "-backend=false", "-input=false"],
            cwd=ROOT,
            env=terraform_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert initialized.returncode == 0, initialized.stdout + initialized.stderr

        validated = subprocess.run(
            [terraform, "-chdir=" + str(PLATFORM_ROOT), "validate"],
            cwd=ROOT,
            env=terraform_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert validated.returncode == 0, validated.stdout + validated.stderr
