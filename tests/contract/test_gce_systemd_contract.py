from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GCE = ROOT / "infra" / "gce"
SYSTEMD = GCE / "systemd"
SYSCTL = SYSTEMD / "99-strayhub-network.conf"
SCRIPTS = GCE / "scripts"
DOC = ROOT / "docs" / "deployment" / "systemd-operations.md"


def _unit(name: str) -> str:
    return (SYSTEMD / name).read_text(encoding="utf-8")


def test_unit_topology_orders_secrets_migration_and_application() -> None:
    secrets = _unit("strayhub-secrets.service")
    migration = _unit("strayhub-migrate.service")
    application = _unit("strayhub.service")

    assert "Type=oneshot" in secrets
    assert "RemainAfterExit=yes" in secrets
    assert "ConditionPathExists=/etc/strayhub/production.env" in secrets
    assert "ConditionPathIsRegular" not in secrets
    assert "User=root" in secrets
    assert "ExecStartPost=/bin/chown -R strayhub:strayhub /var/lib/strayhub/secrets" in secrets
    assert "PrivateTmp=true" in secrets
    assert "Before=strayhub-migrate.service strayhub.service" in secrets
    assert "Requires=docker.service strayhub-secrets.service" in migration
    assert "Before=strayhub.service" in migration
    assert "production-preflight.sh" in migration
    assert "--profile tools run --rm migration" in migration
    assert (
        "Requires=docker.service strayhub-secrets.service strayhub-migrate.service" in application
    )
    assert (
        "After=network-online.target docker.service strayhub-secrets.service "
        "strayhub-migrate.service" in application
    )


def test_main_unit_uses_canonical_compose_and_preserves_volumes() -> None:
    application = _unit("strayhub.service")

    assert "docker-compose.production.yml" in application
    assert "--env-file /etc/strayhub/production.env" in application
    assert "--env-file /var/lib/strayhub/secrets/current/runtime.env" in application
    assert "verify-systemd-runtime.sh" in application
    for service in ("redis", "celery-worker", "celery-beat"):
        assert service in application
    assert " stop --timeout 30" in application
    assert "down -v" not in application
    assert "--volumes" not in application


def test_compose_restart_policy_excludes_one_shot_services() -> None:
    compose = yaml.safe_load((GCE / "docker-compose.production.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    for service in (
        "web",
        "api",
        "worker",
        "postgres",
        "minio",
        "redis",
        "celery-worker",
        "celery-beat",
    ):
        assert services[service]["restart"] == "unless-stopped"
    for service in ("migration", "minio-bootstrap"):
        assert services[service]["restart"] == "no"


def test_backup_timer_is_daily_persistent_and_single_instance() -> None:
    service = _unit("strayhub-backup.service")
    timer = _unit("strayhub-backup.timer")
    runner = (SCRIPTS / "run-systemd-backup.sh").read_text(encoding="utf-8")

    assert "EnvironmentFile=/var/lib/strayhub/secrets/current/runtime.env" in service
    assert (
        "Environment=PATH=/snap/google-cloud-cli/current/bin:/usr/local/sbin:"
        "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" in service
    )
    assert "OnCalendar=*-*-* 03:00:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "flock -n" in runner
    assert "backup-all.sh" in runner
    assert "gcs-backup-preflight.sh" in runner
    assert "upload-backup-gcs.sh" in runner
    assert "storage rm" not in runner


def test_units_contain_no_inline_secrets_or_e4_mutation() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in SYSTEMD.iterdir())

    for forbidden in (
        "POSTGRES_PASSWORD=",
        "MINIO_SECRET_KEY=",
        "LINE_CHANNEL_SECRET=",
        "PRIVATE KEY",
        "certbot",
        "gcloud dns",
        "gcloud compute firewall",
        "terraform apply",
    ):
        assert forbidden not in combined


def test_installer_keeps_repo_units_authoritative_and_does_not_start_runtime() -> None:
    installer = (SCRIPTS / "install-systemd-units.sh").read_text(encoding="utf-8")

    assert "install -o root -g root -m 0644" in installer
    assert "chmod 0750 /etc/strayhub" in installer
    assert "chown -R strayhub:strayhub /var/lib/strayhub/secrets" in installer
    assert "systemctl daemon-reload" in installer
    assert "systemctl enable strayhub.service strayhub-backup.timer" in installer
    assert 'SYSCTL_TARGET="/etc/sysctl.d/99-strayhub-network.conf"' in installer
    assert 'sysctl --load "$SYSCTL_TARGET"' in installer
    assert SYSCTL.read_text(encoding="utf-8").strip().endswith("net.ipv4.ip_forward = 1")
    assert "systemctl start" not in installer
    assert "cat >" not in installer


def test_health_check_is_bounded_and_uses_only_local_routes() -> None:
    health = (SCRIPTS / "verify-systemd-runtime.sh").read_text(encoding="utf-8")

    assert "deadline=$((SECONDS + TIMEOUT))" in health
    assert 'cd "$ROOT_DIR"' in health
    assert "http://127.0.0.1:$port$path" in health
    assert "container_ready nginx" not in health
    for service in ("redis", "celery-worker", "celery-beat"):
        assert f"container_ready {service}" in health
    for route in (
        "/healthz",
        "/v1/public/volunteer-organizations",
        "/volunteer-application",
        "/v1/line/webhook",
    ):
        assert route in health
    assert "strayhub.example.com" not in health


def test_production_preflight_is_independent_of_the_callers_working_directory() -> None:
    preflight = (SCRIPTS / "production-preflight.sh").read_text(encoding="utf-8")

    assert 'cd "$ROOT_DIR"' in preflight


def test_operations_document_failure_gates_and_deferred_cutover() -> None:
    documentation = DOC.read_text(encoding="utf-8")

    for phrase in (
        "secret fetch fails",
        "migration fails",
        "Persistent=true",
        "docker compose stop",
        "journalctl",
        "API failure recovery",
        "Phase E4",
        "strayhub.enadv.quest",
        "34.10.249.63",
    ):
        assert phrase in documentation
