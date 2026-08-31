from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "gce" / "docker-compose.production.yml"
EDGE = ROOT / "infra" / "edge-nginx" / "strayhub.enadv.quest.conf"
NETWORK = ROOT / "infra" / "gce" / "terraform" / "network.tf"
VARIABLES = ROOT / "infra" / "gce" / "terraform" / "variables.tf"


def test_old_vm_is_the_only_canonical_nginx_edge() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    edge = EDGE.read_text(encoding="utf-8")

    assert "nginx" not in compose["services"]
    assert "server_name strayhub.enadv.quest;" in edge
    assert "/etc/letsencrypt/live/strayhub.enadv.quest/fullchain.pem" in edge
    assert "/etc/letsencrypt/live/strayhub.enadv.quest/privkey.pem" in edge


def test_edge_routes_only_to_source_restricted_web_and_api_ports() -> None:
    edge = EDGE.read_text(encoding="utf-8")
    network = NETWORK.read_text(encoding="utf-8")
    variables = VARIABLES.read_text(encoding="utf-8")

    assert "proxy_pass http://34.81.77.204:3000;" in edge
    assert "proxy_pass http://34.81.77.204:8080;" in edge
    assert "source_ranges           = [var.edge_source_cidr]" in network
    assert 'default     = "34.10.249.63/32"' in variables
    assert '"0.0.0.0/0"' not in network
    for forbidden in ("5432", "9000", "9001"):
        assert f'"{forbidden}"' not in network


def test_forwarded_headers_routes_and_security_boundary_are_preserved() -> None:
    edge = EDGE.read_text(encoding="utf-8")

    for required in (
        "location = /healthz",
        "location = /v1",
        "location ^~ /v1/",
        "location /",
        "proxy_http_version 1.1;",
        "proxy_set_header Host $host;",
        "proxy_set_header X-Real-IP $remote_addr;",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "proxy_set_header X-Forwarded-Proto https;",
    ):
        assert required in edge
    for forbidden in ("minio", "postgres", "9000", "9001", "5432", "hmr", "webpack"):
        assert forbidden not in edge.lower()


def test_adjustment_contains_no_dns_tls_line_or_cleanup_mutation() -> None:
    relevant = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            EDGE,
            NETWORK,
            ROOT / "infra" / "gce" / "terraform" / "compute.tf",
        )
    ).lower()

    for forbidden in (
        "gcloud dns",
        "certbot certonly",
        "line_channel_secret",
        "liff url",
        "google_cloud_run",
        "google_sql",
        "terraform state rm",
    ):
        assert forbidden not in relevant
