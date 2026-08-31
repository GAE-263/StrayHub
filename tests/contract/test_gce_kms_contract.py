from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
COMPOSE_PATH = GCE_ROOT / "docker-compose.production.yml"
TEMPLATE_PATH = GCE_ROOT / ".env.production.template"
PREFLIGHT_PATH = GCE_ROOT / "scripts" / "production-preflight.sh"
KMS_DOC_PATH = ROOT / "docs" / "deployment" / "cloud-kms.md"
PII_CIPHER_PATH = (
    ROOT / "services" / "api" / "app" / "infrastructure" / "security" / "pii_cipher.py"
)
LIVE_VERIFY_PATH = GCE_ROOT / "scripts" / "verify-live-kms.py"


def test_production_template_selects_kms_without_credentials() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "PII_ENCRYPTION_PROVIDER=gcp-kms" in template
    assert "PII_KMS_KEY_NAME=" in template
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in template
    assert "service_account" not in template
    assert "private_key" not in template


def test_compose_scopes_kms_configuration_to_api() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

    api_environment = compose["services"]["api"]["environment"]
    assert api_environment["PII_ENCRYPTION_PROVIDER"].startswith("${PII_ENCRYPTION_PROVIDER:")
    assert api_environment["PII_KMS_KEY_NAME"].startswith("${PII_KMS_KEY_NAME:")
    for service_name, service in compose["services"].items():
        if service_name != "api":
            environment = service.get("environment", {})
            assert "PII_ENCRYPTION_PROVIDER" not in environment
            assert "PII_KMS_KEY_NAME" not in environment


def test_production_preflight_validates_kms_without_live_call() -> None:
    preflight = PREFLIGHT_PATH.read_text(encoding="utf-8")

    assert "PII_ENCRYPTION_PROVIDER must remain gcp-kms" in preflight
    assert "PII_KMS_KEY_NAME must be a full Cloud KMS CryptoKey resource name" in preflight
    assert "cryptoKeys/" in preflight
    for forbidden in (
        "gcloud kms",
        "KeyManagementServiceClient",
        ".encrypt(",
        ".decrypt(",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        assert forbidden not in preflight


def test_existing_adapter_uses_adc_client_and_has_no_runtime_fallback() -> None:
    cipher = PII_CIPHER_PATH.read_text(encoding="utf-8")

    assert "kms_v1.KeyManagementServiceClient()" in cipher
    assert 'normalized_provider == "gcp-kms"' in cipher
    assert 'app_env.lower() not in {"local", "test", "testing"}' in cipher
    assert "configured_pii_cipher_from_settings(get_settings())" in (
        ROOT / "services" / "api" / "app" / "api" / "volunteer_access.py"
    ).read_text(encoding="utf-8")


def test_live_verifier_uses_existing_adapter_without_leaking_payloads() -> None:
    verifier = LIVE_VERIFY_PATH.read_text(encoding="utf-8")

    assert "configured_pii_cipher(" in verifier
    assert 'app_env="production"' in verifier
    assert 'provider="gcp-kms"' in verifier
    assert "allow_local_provider=False" in verifier
    assert "pii_ciphertext_invalid" in verifier
    assert "print(plaintext" not in verifier
    assert "print(encrypted" not in verifier
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in verifier


def test_kms_iam_and_live_acceptance_boundaries_are_least_privilege() -> None:
    documentation = KMS_DOC_PATH.read_text(encoding="utf-8")

    for phrase in (
        "GCE VM service account",
        "Application Default Credentials",
        "roles/cloudkms.cryptoKeyEncrypterDecrypter",
        "specific PII CryptoKey",
        "Phase E2 live acceptance",
        "controlled `gcloud` commands",
        "Phase E3",
        "Phase F",
    ):
        assert phrase in documentation
    for forbidden in (
        "roles/editor",
        "roles/owner",
        "roles/cloudkms.admin",
        "service-account json keys are part of the production design",
    ):
        assert forbidden not in documentation.lower()
