from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
COMPOSE_PATH = GCE_ROOT / "docker-compose.production.yml"
NGINX_PATH = ROOT / "infra" / "edge-nginx" / "strayhub.enadv.quest.conf"
ENV_PATH = GCE_ROOT / ".env.production.example"
GENERATOR = GCE_ROOT / "scripts" / "generate-verification-tls-cert.sh"
EDGE_DOC = ROOT / "docs" / "deployment" / "tls-dns-firewall.md"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _nginx() -> str:
    return NGINX_PATH.read_text(encoding="utf-8")


def test_new_gce_has_no_nginx_or_public_http_https() -> None:
    services = _compose()["services"]
    published = {name for name, service in services.items() if service.get("ports")}

    assert published == {"web", "api"}
    assert "nginx" not in services
    for service in ("postgres", "minio", "worker"):
        assert "ports" not in services[service]
    assert {entry["target"] for entry in services["web"]["ports"]} == {8080}
    assert {entry["target"] for entry in services["api"]["ports"]} == {8080}


def test_http_redirect_and_acme_exception_are_explicit() -> None:
    config = _nginx()

    assert "listen 80;" in config
    assert "location ^~ /.well-known/acme-challenge/" in config
    assert "root /var/www/html;" in config
    assert "try_files $uri =404;" in config
    assert "return 301 https://$host$request_uri;" in config
    assert "autoindex on" not in config.lower()


def test_https_terminates_tls_and_preserves_b2_routes() -> None:
    config = _nginx()

    assert "listen 443 ssl;" in config
    assert "ssl_certificate /etc/letsencrypt/live/strayhub.enadv.quest/fullchain.pem;" in config
    assert "ssl_certificate_key /etc/letsencrypt/live/strayhub.enadv.quest/privkey.pem;" in config
    assert "proxy_set_header Host $host;" in config
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in config
    assert "proxy_set_header X-Forwarded-Proto https;" in config
    assert config.count("client_max_body_size 1m;") == 1
    for route in ("location = /healthz", "location = /v1", "location ^~ /v1/", "location /"):
        assert route in config


def test_certificate_stays_on_old_edge_and_upstream_ports_are_explicit() -> None:
    config = _nginx()
    environment = ENV_PATH.read_text(encoding="utf-8")

    assert "/etc/letsencrypt/live/strayhub.enadv.quest/fullchain.pem" in config
    assert "E4_WEB_UPSTREAM_HOST_PORT=3000" in environment
    assert "E4_API_UPSTREAM_HOST_PORT=8080" in environment
    assert "B4_LETSENCRYPT_DIR" not in environment


def test_verification_certificate_is_runtime_generated_ignored_and_private(tmp_path: Path) -> None:
    output = tmp_path / "tls"
    webroot = tmp_path / "acme-webroot"
    environment = {
        **os.environ,
        "STRAYHUB_VERIFICATION_TLS_DIR": str(output),
        "STRAYHUB_VERIFICATION_ACME_WEBROOT": str(webroot),
    }

    subprocess.run([GENERATOR], cwd=ROOT, env=environment, check=True)
    private_key = output / "live" / "strayhub" / "privkey.pem"
    certificate = output / "live" / "strayhub" / "fullchain.pem"
    assert stat.S_IMODE(private_key.stat().st_mode) == 0o600
    assert stat.S_IMODE(certificate.stat().st_mode) == 0o644
    assert (webroot / ".well-known" / "acme-challenge").is_dir()

    subprocess.run(
        ["openssl", "x509", "-in", certificate, "-noout", "-checkend", "86400"],
        check=True,
    )
    first_key = private_key.read_bytes()
    subprocess.run([GENERATOR], cwd=ROOT, env=environment, check=True)
    assert private_key.read_bytes() == first_key
    subprocess.run([GENERATOR, "--force"], cwd=ROOT, env=environment, check=True)
    assert private_key.read_bytes() != first_key
    rotated_key = private_key.read_bytes()
    certificate.write_text("invalid verification certificate\n", encoding="utf-8")
    subprocess.run([GENERATOR], cwd=ROOT, env=environment, check=True)
    assert private_key.read_bytes() != rotated_key
    subprocess.run(
        ["openssl", "x509", "-in", certificate, "-noout", "-checkend", "86400"],
        check=True,
    )

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "infra/gce/verification/generated/tls"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert tracked.returncode != 0
    ignored = subprocess.run(
        [
            "git",
            "check-ignore",
            "-q",
            "infra/gce/verification/generated/tls/live/strayhub/privkey.pem",
        ],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 0
    assert "infra/gce/verification/generated/" in (ROOT / ".dockerignore").read_text(
        encoding="utf-8"
    )


def test_dns_firewall_line_and_certificate_policy_are_documented() -> None:
    documentation = EDGE_DOC.read_text(encoding="utf-8")
    normalized = " ".join(documentation.split())

    for phrase in (
        "34.10.249.63",
        "strayhub.enadv.quest",
        "old edge alone accepts public TCP 80/443",
        "host-level Certbot",
        "Let's Encrypt",
        "https://strayhub.enadv.quest/v1/line/webhook",
        "https://strayhub.enadv.quest/volunteer-application",
        "no DNS mutation",
        "HSTS",
        "Phase E4",
    ):
        assert phrase in normalized
    assert "10.43.0.2" in normalized
    assert "E4 neither issues nor replaces the certificate" in normalized


def test_b4_adds_no_real_gcp_mutation_or_scheduler() -> None:
    changed_runtime = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            COMPOSE_PATH,
            GCE_ROOT / "nginx" / "strayhub.conf",
            GENERATOR,
            GCE_ROOT / "scripts" / "preflight.sh",
        )
    ).lower()

    for forbidden in (
        "gcloud compute",
        "gcloud dns",
        "certbot certonly",
        "systemctl",
        "systemd-run",
        "google_compute_firewall",
        "google_compute_address",
    ):
        assert forbidden not in changed_runtime
