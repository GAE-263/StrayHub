from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
COMPOSE_PATH = GCE_ROOT / "docker-compose.production.yml"
NGINX_PATH = ROOT / "infra" / "edge-nginx" / "strayhub.enadv.quest.conf"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _nginx() -> str:
    return NGINX_PATH.read_text(encoding="utf-8")


def _location(selector: str) -> str:
    matches = list(
        re.finditer(
            rf"location\s+{re.escape(selector)}\s*\{{(?P<body>.*?)\n\s*\}}",
            _nginx(),
            flags=re.DOTALL,
        )
    )
    assert matches
    return matches[-1].group("body")


def test_only_source_restricted_upstreams_are_host_published() -> None:
    services = _compose()["services"]
    published = {name for name, service in services.items() if service.get("ports")}

    assert published == {"web", "api"}
    assert "nginx" not in services
    for private_service in ("postgres", "minio", "worker"):
        assert "ports" not in services[private_service]


def test_old_edge_nginx_is_the_single_routing_source_of_truth() -> None:
    config = _nginx()

    assert "server_name strayhub.enadv.quest;" in config
    assert "listen 443 ssl;" in config
    assert "34.81.77.204:8080" in config
    assert "34.81.77.204:3000" in config


def test_api_routes_preserve_paths_and_web_owns_the_fallback() -> None:
    assert "proxy_pass http://34.81.77.204:8080;" in _location("= /healthz")
    assert "proxy_pass http://34.81.77.204:8080;" in _location("= /v1")
    versioned = _location("^~ /v1/")
    assert "proxy_pass http://34.81.77.204:8080;" in versioned
    assert "proxy_pass http://34.81.77.204:8080/;" not in versioned
    assert "proxy_pass http://34.81.77.204:3000;" in _location("/")


def test_proxy_targets_use_only_new_gce_application_upstreams() -> None:
    targets = re.findall(r"proxy_pass\s+([^;]+);", _nginx())

    assert targets
    assert set(targets) == {"http://34.81.77.204:8080", "http://34.81.77.204:3000"}
    assert not any(
        forbidden in target
        for target in targets
        for forbidden in ("localhost", "127.0.0.1", "host.docker.internal", "minio", "postgres")
    )


def test_forwarded_headers_and_bounded_body_policy_are_configured() -> None:
    config = _nginx()

    assert "proxy_set_header Host $host;" in config
    assert "proxy_set_header X-Real-IP $remote_addr;" in config
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in config
    assert "proxy_set_header X-Forwarded-Proto https;" in config
    assert "client_max_body_size 1m;" in config


def test_production_config_has_no_hmr_or_dev_proxy_behavior() -> None:
    normalized = _nginx().lower()

    for forbidden in ("hmr", "webpack", "upgrade $http_upgrade", "connection_upgrade"):
        assert forbidden not in normalized


def test_line_webhook_and_liff_paths_are_structurally_compatible() -> None:
    webhook = (ROOT / "services" / "api" / "app" / "api" / "line_webhook.py").read_text(
        encoding="utf-8"
    )
    liff_page = (
        ROOT
        / "apps"
        / "web"
        / "app"
        / "(volunteer-onboarding)"
        / "volunteer-application"
        / "page.tsx"
    )

    assert 'APIRouter(prefix="/v1/line"' in webhook
    assert re.search(r'@router\.post\("/webhook"(?:,|\))', webhook)
    assert "proxy_pass http://34.81.77.204:8080;" in _location("^~ /v1/")
    assert liff_page.is_file()
    assert "proxy_pass http://34.81.77.204:3000;" in _location("/")
