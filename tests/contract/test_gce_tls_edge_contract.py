from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
COMPOSE_PATH = GCE_ROOT / "docker-compose.production.yml"
NGINX_PATH = GCE_ROOT / "nginx" / "strayhub.conf"
ENV_PATH = GCE_ROOT / ".env.production.example"
GENERATOR = GCE_ROOT / "scripts" / "generate-verification-tls-cert.sh"
EDGE_DOC = ROOT / "docs" / "deployment" / "tls-dns-firewall.md"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _nginx() -> str:
    return NGINX_PATH.read_text(encoding="utf-8")


def test_only_nginx_publishes_http_and_https() -> None:
    services = _compose()["services"]
    published = {name for name, service in services.items() if service.get("ports")}
    nginx_ports = {entry["target"] for entry in services["nginx"]["ports"]}

    assert published == {"nginx"}
    assert nginx_ports == {80, 443}
    for service in ("web", "api", "postgres", "minio", "worker"):
        assert "ports" not in services[service]


def test_http_redirect_and_acme_exception_are_explicit() -> None:
    config = _nginx()

    assert "listen 80 default_server;" in config
    assert "location ^~ /.well-known/acme-challenge/" in config
    assert "root /var/www/certbot;" in config
    assert "try_files $uri =404;" in config
    assert "return 308 https://$host$request_uri;" in config
    assert "autoindex on" not in config.lower()


def test_https_terminates_tls_and_preserves_b2_routes() -> None:
    config = _nginx()

    assert "listen 443 ssl default_server;" in config
    assert "ssl_certificate /etc/letsencrypt/live/strayhub/fullchain.pem;" in config
    assert "ssl_certificate_key /etc/letsencrypt/live/strayhub/privkey.pem;" in config
    assert "proxy_set_header Host $http_host;" in config
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in config
    assert "proxy_set_header X-Forwarded-Proto https;" in config
    assert config.count("client_max_body_size 1m;") == 2
    for route in ("location = /healthz", "location = /v1", "location ^~ /v1/", "location /"):
        assert route in config


def test_certificate_and_webroot_mounts_are_parameterized_and_read_only() -> None:
    nginx = _compose()["services"]["nginx"]
    mounts = "\n".join(nginx["volumes"])
    environment = ENV_PATH.read_text(encoding="utf-8")

    assert "${B4_LETSENCRYPT_DIR:?B4_LETSENCRYPT_DIR is required}" in mounts
    assert ":/etc/letsencrypt:ro" in mounts
    assert "${B4_ACME_WEBROOT:?B4_ACME_WEBROOT is required}" in mounts
    assert ":/var/www/certbot:ro" in mounts
    assert "B4_HTTP_HOST_PORT=8088" in environment
    assert "B4_HTTPS_HOST_PORT=8443" in environment
    assert "strayhub.example.com" not in environment


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

    for phrase in (
        "reserved GCE static external IP",
        "one canonical public hostname",
        "inbound TCP 80 and 443 only",
        "Host-level Certbot",
        "Let's Encrypt",
        "https://<canonical-host>/v1/line/webhook",
        "https://<canonical-host>/volunteer-application",
        "DNS must resolve",
        "HSTS",
        "Phase E",
    ):
        assert phrase in documentation
    assert "external HTTPS load balancer" in documentation
    assert "B4 does not create or modify records" in documentation


def test_b4_adds_no_real_gcp_mutation_or_scheduler() -> None:
    changed_runtime = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            COMPOSE_PATH,
            NGINX_PATH,
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
