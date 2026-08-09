from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GCP_ROOT = ROOT / "infra" / "gcp-demo"
TERRAFORM_ROOT = GCP_ROOT / "terraform"


def test_gcp_demo_contract_files_and_boundaries_exist() -> None:
    required = {
        "project.md",
        "line-rich-menu.yaml",
        "Dockerfile.api",
        "Dockerfile.web",
        "Dockerfile.worker",
        "deploy-gate.sh",
        "gate-evidence.md",
    }
    assert required <= {path.name for path in GCP_ROOT.iterdir()}
    assert {
        "main.tf",
        "variables.tf",
        "iam.tf",
        "observability.tf",
        "cloud-sql.tf",
        "storage.tf",
        "cloud-run.tf",
        "outputs.tf",
    } <= {path.name for path in TERRAFORM_ROOT.glob("*.tf")}
    assert not list(GCP_ROOT.glob("cloud-run-*.yaml"))


def test_gcp_demo_contract_has_secret_and_tenant_boundaries() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in GCP_ROOT.rglob("*")
        if path.is_file() and ".terraform" not in path.parts and path.name != "deploy-gate.sh"
    )

    for required in (
        "ORG-A",
        "ORG-B",
        "Secret Manager",
        "asia-east1",
        "secretmanager.googleapis.com",
        "roles/cloudsql.client",
        "roles/storage.objectAdmin",
        "public_access_prevention",
        "uniform_bucket_level_access",
        "google_cloud_run_v2_service",
        "sensitive = true",
    ):
        assert required in text

    forbidden = (
        "-----BEGIN",
        "sk-",
        "AKIA",
        "local-only-password",
        "LINE_CHANNEL_ACCESS_TOKEN=",
    )
    assert not any(value in text for value in forbidden)


def test_demo_build_workflow_never_applies_terraform() -> None:
    workflow = (ROOT / ".github/workflows/demo-build.yml").read_text(encoding="utf-8")
    assert "terraform fmt -check" in workflow
    assert "terraform validate" in workflow
    assert "docker build" in workflow
    assert "terraform apply" not in workflow
    assert "terraform plan" not in workflow


def test_terraform_format_and_validate() -> None:
    terraform = os.environ.get("TERRAFORM_BIN") or shutil.which("terraform")
    assert terraform, "T236 需要 terraform CLI；請安裝後重新執行 Contract Test"

    formatted = subprocess.run(
        [terraform, "fmt", "-check", "-recursive", str(TERRAFORM_ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert formatted.returncode == 0, formatted.stdout + formatted.stderr

    initialized = subprocess.run(
        [terraform, "-chdir=" + str(TERRAFORM_ROOT), "init", "-backend=false", "-input=false"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr

    validated = subprocess.run(
        [terraform, "-chdir=" + str(TERRAFORM_ROOT), "validate"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr
