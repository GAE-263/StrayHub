from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
MAP_PATH = GCE_ROOT / "secrets" / "production-secret-map.tsv"
TEMPLATE_PATH = GCE_ROOT / ".env.production.template"
COMPOSE_PATH = GCE_ROOT / "docker-compose.production.yml"
FETCH_SCRIPT = GCE_ROOT / "scripts" / "fetch-secrets.sh"
PREFLIGHT_SCRIPT = GCE_ROOT / "scripts" / "production-preflight.sh"
DOC_PATH = ROOT / "docs" / "deployment" / "secret-manager.md"

REQUIRED_SCALARS = {
    "POSTGRES_PASSWORD",
    "POSTGRES_RUNTIME_PASSWORD",
    "DATABASE_URL",
    "DATABASE_MIGRATION_URL",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "LINE_CHANNEL_SECRET",
    "LINE_CHANNEL_ACCESS_TOKEN",
    "ANIMAL_CONFIRMATION_SECRET",
    "REDIS_PASSWORD",
    "CELERY_BROKER_URL",
}
REQUIRED_FILES = {
    "AUTH_JWT_ACTIVE_PRIVATE_KEY": "jwt-private.pem",
    "AUTH_JWT_ACTIVE_PUBLIC_KEY": "jwt-public.pem",
}


def _mapping() -> list[tuple[str, str, str, str, str]]:
    entries = []
    for line in MAP_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        entries.append(tuple(line.split("|")))
    return entries


def _write_source(source: Path, *, database_suffix: str = "one") -> dict[str, str]:
    source.mkdir()
    values = {
        "POSTGRES_PASSWORD": "D1SyntheticMigration-7Qm9Vt4Kp2Hs",
        "POSTGRES_RUNTIME_PASSWORD": "D1SyntheticRuntime-8Rx4Kn6Vp9Ts",
        "DATABASE_URL": (
            "postgresql+asyncpg://strayhub_app:D1SyntheticRuntime-8Rx4Kn6Vp9Ts@"
            f"postgres:5432/strayhub_{database_suffix}"
        ),
        "DATABASE_MIGRATION_URL": (
            "postgresql+asyncpg://strayhub_migration:D1SyntheticMigration-7Qm9Vt4Kp2Hs@"
            f"postgres:5432/strayhub_{database_suffix}"
        ),
        "MINIO_ACCESS_KEY": "d1syntheticaccess2026",
        "MINIO_SECRET_KEY": "D1SyntheticStorage-8Rm4Wq7Ts2Kp9Nv6",
        "LINE_CHANNEL_SECRET": "d1synthetic-line-secret-6Tp9Qm3Vs8Kn4Rx7",
        "LINE_CHANNEL_ACCESS_TOKEN": "d1synthetic-line-token-7Qm9Vt4Kp2Hs6Nx8",
        "ANIMAL_CONFIRMATION_SECRET": "d1synthetic-confirmation-6Tp9Qm3Vs8Kn4Rx7",
        "REDIS_PASSWORD": "D1SyntheticRedis-4Qm8Vs2Kn7Tp",
        "CELERY_BROKER_URL": ("redis://:D1SyntheticRedis-4Qm8Vs2Kn7Tp@redis:6379/0"),
    }
    suffixes = {runtime_name: suffix for _, runtime_name, suffix, _, _ in _mapping()}
    for runtime_name, value in values.items():
        (source / f"strayhub-prod-{suffixes[runtime_name]}").write_text(value, encoding="utf-8")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (source / f"strayhub-prod-{suffixes['AUTH_JWT_ACTIVE_PRIVATE_KEY']}").write_bytes(private_pem)
    (source / f"strayhub-prod-{suffixes['AUTH_JWT_ACTIVE_PUBLIC_KEY']}").write_bytes(public_pem)
    return values


def _fetch(source: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            FETCH_SCRIPT,
            "--environment",
            "prod",
            "--source-dir",
            source,
            "--output-root",
            output,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_required_inventory_and_secret_id_suffixes_are_declarative() -> None:
    entries = _mapping()
    required_env = {
        name
        for transport, name, _, _, required in entries
        if transport == "env" and required == "required"
    }
    required_files = {
        name: filename
        for transport, name, _, filename, required in entries
        if transport == "file" and required == "required"
    }

    assert required_env == REQUIRED_SCALARS
    assert required_files == REQUIRED_FILES
    assert ("env", "AI_API_KEY", "ai-api-key", "-", "optional") in entries
    assert ("env", "GEMINI_API_KEY", "gemini-api-key", "-", "optional") in entries
    assert ("env", "STOOL_API_KEY", "stool-api-key", "-", "optional") in entries
    for _, _, suffix, _, _ in entries:
        assert suffix.startswith("strayhub-") is False
        assert "project" not in suffix


def test_production_template_is_nonsecret_and_distinct_from_b1_verification() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "B1_VERIFICATION_ONLY=false" in template
    assert "APP_ENV=production" in template
    assert "LINE_ROLE_MENU_FEATURES_ENABLED=false" in template
    assert "verification/generated" not in template
    assert "/var/lib/strayhub/secrets/current/jwt-private.pem" in template
    assert "/var/lib/strayhub/secrets/current/jwt-public.pem" in template
    for secret_name in REQUIRED_SCALARS | {"AI_API_KEY", "GEMINI_API_KEY", "STOOL_API_KEY"}:
        assert f"{secret_name}=" not in template


def test_synthetic_fetch_stages_atomic_private_generations(tmp_path: Path) -> None:
    source_one = tmp_path / "source-one"
    output = tmp_path / "staged"
    values_one = _write_source(source_one, database_suffix="one")
    first = _fetch(source_one, output)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "PASS" in first.stdout
    assert not any(value in first.stdout + first.stderr for value in values_one.values())

    current = output / "current"
    first_generation = current.resolve()
    assert current.is_symlink()
    assert first_generation.parent == output / "generations"
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    for name in ("runtime.env", "jwt-private.pem", "jwt-public.pem"):
        assert stat.S_IMODE((current / name).stat().st_mode) == 0o600
    runtime_env = (current / "runtime.env").read_text(encoding="utf-8")
    for secret_name, value in values_one.items():
        assert f"{secret_name}=" in runtime_env
        assert value in runtime_env
    assert "AI_API_KEY=" not in runtime_env

    source_two = tmp_path / "source-two"
    _write_source(source_two, database_suffix="two")
    second = _fetch(source_two, output)
    assert second.returncode == 0, second.stdout + second.stderr
    second_generation = current.resolve()
    assert second_generation != first_generation
    assert first_generation.is_dir()
    assert "strayhub_two" in (current / "runtime.env").read_text(encoding="utf-8")


def test_missing_required_secret_does_not_replace_current_generation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "staged"
    _write_source(source)
    assert _fetch(source, output).returncode == 0
    active_before = (output / "current").resolve()
    (source / "strayhub-prod-database-url").unlink()

    failed = _fetch(source, output)
    assert failed.returncode != 0
    assert "required secret is missing or empty" in failed.stderr
    assert (output / "current").resolve() == active_before


def test_fetch_is_read_only_and_never_places_secret_values_on_arguments() -> None:
    script = FETCH_SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "umask 077" in script
    assert "secrets versions access latest" in script
    assert '>"$destination"' in script
    assert 'chmod 600 "$destination"' in script
    assert "os.replace(sys.argv[1], sys.argv[2])" in script
    for forbidden in (
        "secrets create",
        "secrets versions add",
        "add-iam-policy-binding",
        "set-iam-policy",
        "set -x",
    ):
        assert forbidden not in script


def test_compose_uses_generic_selected_jwt_files_and_scalar_secret_inputs() -> None:
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    api = compose["services"]["api"]

    assert "verification/generated" not in compose_text
    assert "cloud run" not in compose_text.lower()
    assert compose["secrets"]["runtime_jwt_private_key"]["file"].startswith(
        "${AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE:"
    )
    assert compose["secrets"]["runtime_jwt_public_key"]["file"].startswith(
        "${AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE:"
    )
    assert api["environment"]["AI_API_KEY"] == "${AI_API_KEY:-}"
    assert api["environment"]["LINE_ROLE_MENU_FEATURES_ENABLED"] == (
        "${LINE_ROLE_MENU_FEATURES_ENABLED:-false}"
    )
    assert api["environment"]["LINE_ROLE_MENU_SMOKE_EVIDENCE"] == (
        "${LINE_ROLE_MENU_SMOKE_EVIDENCE:-}"
    )
    assert compose["services"]["worker"]["environment"]["LINE_CHANNEL_ACCESS_TOKEN"] == (
        "${LINE_CHANNEL_ACCESS_TOKEN:-}"
    )
    assert compose["services"]["worker"]["environment"]["DATABASE_URL"].startswith(
        "${DATABASE_URL:"
    )
    assert compose["services"]["migration"]["environment"]["DATABASE_URL"].startswith(
        "${DATABASE_MIGRATION_URL:"
    )


def test_production_preflight_enforces_mode_separation_and_consumption_checks() -> None:
    preflight = PREFLIGHT_SCRIPT.read_text(encoding="utf-8")

    assert "B1_VERIFICATION_ONLY must be false" in preflight
    assert "verification-only material" in preflight
    assert "secret staging root mode must be 0700" in preflight
    assert "staged secret file mode must be 0600" in preflight
    assert "config --quiet" in preflight
    assert 'validate_runtime_safety(process=\\"api\\")' in preflight
    assert 'validate_runtime_safety(process="worker")' in preflight
    assert 'validate_runtime_safety(process="migration")' in preflight
    assert "LINE_ROLE_MENU_FEATURES_ENABLED must be exactly true or false" in preflight
    assert "LINE_ROLE_MENU_SMOKE_EVIDENCE must identify" in preflight
    assert preflight.index('line_features_enabled" == "true"') < preflight.index(
        'LINE_ROLE_MENU_SMOKE_EVIDENCE)"'
    )
    assert '--env-file "$CONFIG_ENV"' in preflight
    assert '--env-file "$runtime_env"' in preflight
    assert preflight.index("stat -c '%a'") < preflight.index("stat -f '%Lp'")


def test_documentation_limits_iam_and_defers_live_gcp_mutation() -> None:
    documentation = DOC_PATH.read_text(encoding="utf-8")

    for phrase in (
        "roles/secretmanager.secretAccessor",
        "secret-level IAM",
        "/var/lib/strayhub/secrets",
        "directory mode `0700`",
        "file mode `0600`",
        "runtime-generated verification JWT",
        "Phase E2 live acceptance",
        "does not create or mutate secrets",
        "container environment",
    ):
        assert phrase in documentation
    for forbidden in ("roles/editor", "roles/owner"):
        assert forbidden not in documentation
