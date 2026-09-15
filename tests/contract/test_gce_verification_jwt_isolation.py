from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
VERIFICATION_ROOT = GCE_ROOT / "verification"
GENERATED_ROOT = VERIFICATION_ROOT / "generated"
GENERATOR = GCE_ROOT / "scripts" / "generate-verification-jwt-keys.sh"

EXCLUDED_PARTS = {
    ".git",
    ".next",
    ".terraform",
    ".venv",
    "node_modules",
    "test-results",
}
REFERENCE_ALLOWLIST = {
    ".dockerignore",
    ".gitignore",
    "docs/deployment/deployment-source-of-truth-plan.md",
    "docs/deployment/production-config-contract.md",
    "docs/deployment/acceptance-isolation.md",
    "docs/deployment/secret-manager.md",
    "docs/deployment/local-staging.md",
    "docs/deployment/tls-dns-firewall.md",
    "infra/gce/.env.production.template",
    "infra/gce/.env.production.example",
    "infra/gce/.env.acceptance.template",
    "infra/local/staging.env.template",
    "infra/gce/scripts/acceptance-preflight.sh",
    "infra/gce/scripts/fetch-secrets.sh",
    "infra/gce/scripts/deploy-release.sh",
    "infra/gce/scripts/generate-verification-jwt-keys.sh",
    "infra/gce/scripts/generate-verification-tls-cert.sh",
    "infra/gce/scripts/preflight.sh",
    "infra/gce/scripts/production-preflight.sh",
    "infra/gce/secrets/production-secret-map.tsv",
    "infra/gce/secrets/acceptance-secret-map.tsv",
    "infra/gce/verification/README.md",
    "review.md",
    # Executes deployment prerequisites in tmp_path with non-credential text;
    # never reads or generates real signing keys.
    "tests/contract/test_deploy_release_failures.py",
    "tests/contract/test_gce_production_compose_contract.py",
    "tests/contract/test_gce_secret_manager_contract.py",
    "tests/contract/test_gce_tls_edge_contract.py",
    "tests/contract/test_gce_verification_jwt_isolation.py",
}


def _text_files() -> list[Path]:
    paths: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if GENERATED_ROOT in path.parents or path.stat().st_size > 1_000_000:
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        paths.append(path)
    return paths


def _run_generator(output_dir: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [GENERATOR, *arguments],
        cwd=ROOT,
        env={**os.environ, "STRAYHUB_VERIFICATION_JWT_DIR": str(output_dir)},
        capture_output=True,
        text=True,
        check=False,
    )


def _load_pair(output_dir: Path) -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = serialization.load_pem_private_key(
        (output_dir / "jwt-private.pem").read_bytes(), password=None
    )
    public_key = serialization.load_pem_public_key((output_dir / "jwt-public.pem").read_bytes())
    assert isinstance(private_key, rsa.RSAPrivateKey)
    assert isinstance(public_key, rsa.RSAPublicKey)
    return private_key, public_key


def test_generator_creates_reuses_and_force_rotates_valid_rsa_pair(tmp_path: Path) -> None:
    output_dir = tmp_path / "generated"

    generated = _run_generator(output_dir)
    assert generated.returncode == 0, generated.stdout + generated.stderr
    assert "Generated fresh RSA 2048 keypair" in generated.stdout
    assert "BEGIN" not in generated.stdout + generated.stderr
    private_key, public_key = _load_pair(output_dir)
    assert private_key.key_size == 2048
    assert public_key.key_size == 2048
    assert private_key.public_key().public_numbers() == public_key.public_numbers()
    assert stat.S_IMODE((output_dir / "jwt-private.pem").stat().st_mode) == 0o600
    assert stat.S_IMODE((output_dir / "jwt-public.pem").stat().st_mode) == 0o644
    original_private = (output_dir / "jwt-private.pem").read_bytes()
    original_public = (output_dir / "jwt-public.pem").read_bytes()

    reused = _run_generator(output_dir)
    assert reused.returncode == 0, reused.stdout + reused.stderr
    assert "Reusing valid RSA 2048 keypair" in reused.stdout
    assert (output_dir / "jwt-private.pem").read_bytes() == original_private
    assert (output_dir / "jwt-public.pem").read_bytes() == original_public

    rotated = _run_generator(output_dir, "--force")
    assert rotated.returncode == 0, rotated.stdout + rotated.stderr
    assert "Generated fresh RSA 2048 keypair" in rotated.stdout
    assert (output_dir / "jwt-private.pem").read_bytes() != original_private
    assert (output_dir / "jwt-public.pem").read_bytes() != original_public
    rotated_private, rotated_public = _load_pair(output_dir)
    assert rotated_private.public_key().public_numbers() == rotated_public.public_numbers()

    rotated_private_bytes = (output_dir / "jwt-private.pem").read_bytes()
    (output_dir / "jwt-public.pem").write_text(
        "invalid verification public key\n", encoding="utf-8"
    )
    repaired = _run_generator(output_dir)
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    assert "Generated fresh RSA 2048 keypair" in repaired.stdout
    assert (output_dir / "jwt-private.pem").read_bytes() != rotated_private_bytes
    repaired_private, repaired_public = _load_pair(output_dir)
    assert repaired_private.public_key().public_numbers() == repaired_public.public_numbers()


def test_pem_fixtures_are_absent_and_generated_paths_are_gitignored() -> None:
    assert not (VERIFICATION_ROOT / "jwt-private.pem").exists()
    assert not (VERIFICATION_ROOT / "jwt-public.pem").exists()
    tracked = subprocess.run(
        ["git", "ls-files", "infra/gce/verification"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "infra/gce/verification/jwt-private.pem" not in tracked
    assert "infra/gce/verification/jwt-public.pem" not in tracked

    for generated_path in (
        "infra/gce/verification/generated/jwt-private.pem",
        "infra/gce/verification/generated/jwt-public.pem",
    ):
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", generated_path],
            cwd=ROOT,
            check=False,
        )
        assert ignored.returncode == 0


def test_generated_key_references_stay_on_the_reviewed_allowlist() -> None:
    references: set[str] = set()
    needles = (
        "jwt-private.pem",
        "jwt-public.pem",
        "infra/gce/verification/generated",
    )
    for path in _text_files():
        text = path.read_text(encoding="utf-8")
        if any(needle in text for needle in needles):
            references.add(path.relative_to(ROOT).as_posix())

    assert references <= REFERENCE_ALLOWLIST
    assert "infra/gce/scripts/generate-verification-jwt-keys.sh" in references
    assert "infra/gce/.env.production.example" in references
    assert "infra/gce/verification/README.md" in references


def test_preflight_generates_only_the_expected_ignored_paths() -> None:
    preflight = (GCE_ROOT / "scripts" / "preflight.sh").read_text(encoding="utf-8")
    environment = (GCE_ROOT / ".env.production.example").read_text(encoding="utf-8")

    assert "generate-verification-jwt-keys.sh" in preflight
    assert '"$KEY_GENERATOR"' in preflight
    assert "B1_VERIFICATION_ONLY=true" in environment
    assert "./verification/generated/jwt-private.pem" in environment
    assert "./verification/generated/jwt-public.pem" in environment
    assert "NOT FOR REAL DEPLOYMENT" in environment


def test_compose_requires_selected_key_files_and_mounts_only_into_api() -> None:
    compose_path = GCE_ROOT / "docker-compose.production.yml"
    compose_text = compose_path.read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)

    assert "verification/generated" not in compose_text
    assert compose["secrets"]["runtime_jwt_private_key"]["file"].startswith(
        "${AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE:"
    )
    assert compose["secrets"]["runtime_jwt_public_key"]["file"].startswith(
        "${AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE:"
    )
    assert compose["services"]["api"]["secrets"] == [
        {
            "source": "runtime_jwt_private_key",
            "target": "runtime_jwt_private_key",
            "mode": 0o400,
        },
        {
            "source": "runtime_jwt_public_key",
            "target": "runtime_jwt_public_key",
            "mode": 0o444,
        },
    ]
    for service_name, service in compose["services"].items():
        if service_name != "api":
            assert "secrets" not in service


def test_production_contract_keeps_generated_keys_out_of_real_deployment() -> None:
    warning = (VERIFICATION_ROOT / "README.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/deployment/production-config-contract.md").read_text(encoding="utf-8")
    normalized_warning = " ".join(warning.split())
    normalized_contract = " ".join(contract.split())

    for phrase in (
        "RUNTIME-GENERATED VERIFICATION MATERIAL",
        "No private or public PEM fixture is committed",
        "MUST NOT be used",
        "MUST NOT be uploaded to Secret Manager",
        "Real deployments must inject",
    ):
        assert phrase in normalized_warning
    assert "No verification PEM is committed" in normalized_contract
    assert "Real GCE must stage JWT values from Secret Manager" in normalized_contract


def test_generated_keys_are_excluded_from_images_without_secret_scan_exception() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    scanner = (ROOT / "scripts/verify_local.sh").read_text(encoding="utf-8")

    assert "infra/gce/verification/generated/" in dockerignore
    assert "!infra/gce/verification/jwt-private.pem" not in scanner
    assert "verification/generated" not in scanner
    for dockerfile in (ROOT / "infra").rglob("Dockerfile*"):
        copy_lines = [line.strip() for line in dockerfile.read_text(encoding="utf-8").splitlines()]
        assert "COPY . ." not in copy_lines
        assert not any("infra/gce" in line or "jwt-private.pem" in line for line in copy_lines)


def test_terraform_and_real_deploy_scripts_do_not_consume_generated_keys() -> None:
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for terraform_root in (
            ROOT / "infra/gce/terraform",
            ROOT / "infra/gcp-platform/terraform",
        )
        for path in terraform_root.glob("*.tf")
    )
    verification_only = {
        "generate-verification-jwt-keys.sh",
        "generate-verification-tls-cert.sh",
        "preflight.sh",
    }
    deploy_scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "infra/gce/scripts").glob("*.sh")
        if path.name not in verification_only
    )

    for text in (terraform, deploy_scripts):
        assert "verification/generated/jwt-private.pem" not in text
        assert "verification/generated/jwt-public.pem" not in text
        assert "gcloud secrets versions add" not in text.lower()
