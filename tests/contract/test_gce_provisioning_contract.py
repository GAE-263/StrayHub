from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TF_ROOT = ROOT / "infra" / "gce" / "terraform"
DOC = ROOT / "docs" / "deployment" / "gce-provisioning.md"
PREFLIGHT = ROOT / "infra" / "gce" / "scripts" / "gce-terraform-preflight.sh"


def _terraform() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(TF_ROOT.rglob("*"))
        if path.is_file() and ".terraform" not in path.parts
    )


def _tf_configuration() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(TF_ROOT.glob("*.tf")))


def test_gce_terraform_source_is_isolated_and_complete() -> None:
    expected = {
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "network.tf",
        "compute.tf",
        "iam.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    }

    assert expected <= {path.name for path in TF_ROOT.iterdir()}
    assert 'backend "local"' in (TF_ROOT / "versions.tf").read_text(encoding="utf-8")
    assert "infra/gcp-demo" not in _tf_configuration()


def test_location_machine_disk_and_static_ip_contract() -> None:
    variables = (TF_ROOT / "variables.tf").read_text(encoding="utf-8")
    compute = (TF_ROOT / "compute.tf").read_text(encoding="utf-8")

    for required in (
        'default     = "asia-east1"',
        'default     = "asia-east1-b"',
        'default     = "e2-medium"',
        'default     = "pd-balanced"',
        "var.boot_disk_size_gb >= 30",
        'default     = "ubuntu-2404-lts-amd64"',
        'resource "google_compute_address" "gce"',
        "nat_ip       = google_compute_address.gce.address",
        "auto_delete = true",
    ):
        assert required in variables + compute


def test_network_ingress_is_edge_restricted_and_iap_only() -> None:
    network = (TF_ROOT / "network.tf").read_text(encoding="utf-8")
    variables = (TF_ROOT / "variables.tf").read_text(encoding="utf-8")

    assert "auto_create_subnetworks = false" in network
    assert 'resource "google_compute_firewall" "edge_upstreams"' in network
    assert "source_ranges           = [var.edge_source_cidr]" in network
    assert 'default     = "34.10.249.63/32"' in variables
    assert "tostring(var.web_upstream_port)" in network
    assert "tostring(var.api_upstream_port)" in network
    assert "source_ranges           = [var.iap_ssh_source_range]" in network
    assert 'ports    = ["22"]' in network
    assert '"0.0.0.0/0"' not in network
    for forbidden_port in ("80", "443", "3001", "8000", "8001", "5432", "9000", "9001"):
        assert f'"{forbidden_port}"' not in network


def test_dedicated_adc_identity_has_no_key_or_broad_iam() -> None:
    terraform = _tf_configuration()
    compute = (TF_ROOT / "compute.tf").read_text(encoding="utf-8")

    assert 'resource "google_service_account" "runtime"' in terraform
    assert 'default     = "strayhub-gce-sa"' in terraform
    assert "cloud-platform" in compute
    for forbidden in (
        "google_service_account_key",
        "google_project_iam",
        "roles/owner",
        "roles/editor",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        assert forbidden not in terraform.lower()


def test_plan_does_not_own_legacy_or_managed_service_resources() -> None:
    terraform = _tf_configuration()

    for forbidden in (
        "google_cloud_run",
        "google_sql",
        "google_storage_bucket",
        "google_kms",
        "google_secret_manager",
        "google_project_service",
        "terraform apply",
        "terraform destroy",
    ):
        assert forbidden not in terraform.lower()


def test_bootstrap_is_non_secret_and_does_not_deploy_the_application() -> None:
    bootstrap = (TF_ROOT / "scripts" / "bootstrap-host.sh.tftpl").read_text(encoding="utf-8")

    for required in (
        "docker-compose-plugin",
        "/opt/strayhub/compose",
        "/var/lib/strayhub/secrets",
        "/var/lib/strayhub/backups",
        "chmod 0600 /swapfile",
        "vm.swappiness=10",
        "gpg --batch --yes --dearmor",
    ):
        assert required in bootstrap
    for forbidden in (
        "LINE_CHANNEL",
        "PRIVATE KEY",
        "docker compose up",
        "git clone",
        "fetch-secrets.sh",
    ):
        assert forbidden not in bootstrap


def test_bootstrap_mutations_are_repeat_safe() -> None:
    bootstrap = (TF_ROOT / "scripts" / "bootstrap-host.sh.tftpl").read_text(encoding="utf-8")

    for required in (
        "gpg --batch --yes --dearmor",
        ">/etc/apt/sources.list.d/docker.list",
        "if ! id strayhub >/dev/null 2>&1; then",
        "install -d -o strayhub -g strayhub",
        "if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then",
        "grep -q '^/swapfile ' /etc/fstab || printf",
        ">/etc/sysctl.d/99-strayhub.conf",
    ):
        assert required in bootstrap
    assert "|| true" not in bootstrap


def test_preflight_is_read_only_and_checks_identity_location_and_collisions() -> None:
    text = PREFLIGHT.read_text(encoding="utf-8")

    assert PREFLIGHT.stat().st_mode & 0o111
    for required in (
        "gcloud auth list",
        "gcloud config get-value project",
        "compute regions describe",
        "compute zones describe",
        "target resource name collision detected",
    ):
        assert required in text
    for forbidden in (
        " create ",
        " update ",
        " delete ",
        " add-iam-policy-binding",
        "services enable",
    ):
        assert forbidden not in text


def test_docs_keep_accepted_host_and_deferred_boundaries_explicit() -> None:
    documentation = " ".join(DOC.read_text(encoding="utf-8").split())

    for required in (
        "Phase E1 accepted",
        "IAP TCP forwarding",
        "no JSON key",
        "one add, zero changes, and one destroy",
        "explicit second execution",
        "final Terraform plan reports no changes",
        "Retired legacy GCP-demo source was never instantiated",
        "E2 live Secret Manager/KMS/GCS acceptance",
    ):
        assert required in documentation


def test_terraform_state_and_operator_plan_files_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".terraform/" in gitignore
    assert "*.tfstate*" in gitignore
    assert "*.tfvars" in gitignore
    assert "*.tfplan" in gitignore
