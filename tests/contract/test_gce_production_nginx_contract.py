from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
COMPOSE_PATH = GCE_ROOT / "docker-compose.production.yml"
NGINX_PATH = GCE_ROOT / "nginx" / "strayhub.conf"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def _nginx() -> str:
    return NGINX_PATH.read_text(encoding="utf-8")


def _location(selector: str) -> str:
    match = re.search(
        rf"location\s+{re.escape(selector)}\s*\{{(?P<body>.*?)\n\s*\}}",
        _nginx(),
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group("body")


def test_nginx_is_the_only_host_published_service() -> None:
    services = _compose()["services"]
    published = {name for name, service in services.items() if service.get("ports")}

    assert published == {"nginx"}
    for private_service in ("web", "api", "postgres", "minio", "worker"):
        assert "ports" not in services[private_service]


def test_nginx_uses_a_pinned_image_and_read_only_config_mount() -> None:
    nginx = _compose()["services"]["nginx"]

    assert nginx["image"] == "nginx:1.27.5-alpine"
    assert nginx["volumes"] == [
        "./nginx/strayhub.conf:/etc/nginx/conf.d/default.conf:ro",
        "${B4_LETSENCRYPT_DIR:?B4_LETSENCRYPT_DIR is required}:/etc/letsencrypt:ro",
        "${B4_ACME_WEBROOT:?B4_ACME_WEBROOT is required}:/var/www/certbot:ro",
    ]
    assert nginx["depends_on"]["api"]["condition"] == "service_healthy"
    assert nginx["depends_on"]["web"]["condition"] == "service_healthy"


def test_api_routes_preserve_paths_and_web_owns_the_fallback() -> None:
    assert "proxy_pass http://api:8080;" in _location("= /healthz")
    assert "proxy_pass http://api:8080;" in _location("= /v1")
    versioned = _location("^~ /v1/")
    assert "proxy_pass http://api:8080;" in versioned
    assert "proxy_pass http://api:8080/;" not in versioned
    assert "proxy_pass http://web:8080;" in _location("/")


def test_proxy_targets_use_compose_dns_without_private_service_routes() -> None:
    targets = re.findall(r"proxy_pass\s+([^;]+);", _nginx())

    assert targets
    assert set(targets) == {"http://api:8080", "http://web:8080"}
    assert not any(
        forbidden in target
        for target in targets
        for forbidden in ("localhost", "127.0.0.1", "host.docker.internal")
    )
    assert not any(
        private_target in target for target in targets for private_target in ("minio", "postgres")
    )


def test_forwarded_headers_and_bounded_body_policy_are_configured() -> None:
    config = _nginx()

    assert "proxy_set_header Host $http_host;" in config
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
    assert "proxy_pass http://api:8080;" in _location("^~ /v1/")
    assert liff_page.is_file()
    assert "proxy_pass http://web:8080;" in _location("/")
