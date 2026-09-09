from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_ROOT = ROOT / "infra" / "gcp-platform" / "terraform"


def _read(name: str) -> str:
    return (PLATFORM_ROOT / name).read_text(encoding="utf-8")


def test_platform_root_owns_only_retained_resources() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PLATFORM_ROOT.glob("*.tf"))

    assert 'bucket = "strayhub-platform-tfstate-canvas-primacy-502703-k1"' in source
    assert 'prefix = "strayhub/platform"' in source
    assert source.count("strayhub-prod-") == 16
    assert '"strayhub-prod-login-abuse-hmac-secret"' in source
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


def test_legacy_source_is_removed_without_weakening_current_release() -> None:
    assert not (ROOT / "infra/gcp-demo").exists()
    assert not (ROOT / ".github/workflows/demo-build.yml").exists()
    assert not (ROOT / "tests/contract/test_gcp_iac_contract.py").exists()
    assert not (ROOT / "tests/integration/test_gcp_demo_smoke.py").exists()

    workflow = (ROOT / ".github/workflows/gce-release.yml").read_text(encoding="utf-8")
    compose = (ROOT / "infra/gce/docker-compose.production.yml").read_text(encoding="utf-8")
    for source in (workflow, compose):
        assert "infra/gcp-demo" not in source
        assert "infra/gce/images/Dockerfile.api" in source
        assert "infra/gce/images/Dockerfile.worker" in source
        assert "infra/gce/images/Dockerfile.web" in source
    assert "terraform apply" not in workflow


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
