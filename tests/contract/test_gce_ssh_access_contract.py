from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TF_ROOT = ROOT / "infra" / "gce" / "terraform"
COMPUTE = TF_ROOT / "compute.tf"
NETWORK = TF_ROOT / "network.tf"
DOC = ROOT / "docs" / "deployment" / "systemd-operations.md"


def test_os_login_is_the_single_ssh_authorization_mechanism() -> None:
    compute = COMPUTE.read_text(encoding="utf-8")

    assert 'enable-oslogin         = "TRUE"' in compute
    assert 'block-project-ssh-keys = "TRUE"' in compute
    assert '\n    "ssh-keys"' not in compute
    assert "rose" not in compute


def test_ssh_ingress_remains_iap_only() -> None:
    network = NETWORK.read_text(encoding="utf-8")

    assert "source_ranges           = [var.iap_ssh_source_range]" in network
    assert 'ports    = ["22"]' in network
    assert '"0.0.0.0/0"' not in network


def test_operator_key_ownership_is_documented_without_private_material() -> None:
    documentation = DOC.read_text(encoding="utf-8")

    assert "b97502027_gmail_com" in documentation
    assert "OS Login" in documentation
    assert "SHA256:1pQPrAV7PeZS7v9Jue457oP9HW9KtADYkAnGsfkaGec" in documentation
    assert "private key" in documentation
    assert "BEGIN OPENSSH PRIVATE KEY" not in documentation


def test_terraform_creates_no_key_material() -> None:
    terraform = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(TF_ROOT.glob("*.tf"))
    ).lower()

    for forbidden in (
        "tls_private_key",
        "google_service_account_key",
        "private_key",
        "local_file",
    ):
        assert forbidden not in terraform
