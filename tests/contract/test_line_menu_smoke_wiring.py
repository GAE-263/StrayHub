"""Scope wiring and candidate identity checks, no Docker runtime or remote calls."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_production_scope_shared_only_with_legacy_worker():
    services = yaml.safe_load((ROOT / "infra/gce/docker-compose.production.yml").read_text())[
        "services"
    ]
    keys = (
        "LINE_STAFF_MENU_ENABLED",
        "LINE_ROLE_MENU_TEST_ENABLED",
        "LINE_ROLE_MENU_TEST_CHANNEL_ID",
        "LINE_ROLE_MENU_BOT_SHA256",
        "LINE_ROLE_MENU_TEST_USER_SHA256",
        "LINE_ROLE_MENU_TEST_EXPIRES_AT",
        "LINE_CHANNEL_ID",
        "LINE_RICH_MENU_STAFF_ID",
    )
    for key in keys:
        assert services["api"]["environment"][key] == services["worker"]["environment"][key]
        if key != "LINE_CHANNEL_ID":
            for name in ("celery-worker", "celery-beat", "web"):
                assert key not in services[name]["environment"]
    mounts = services["api"]["volumes"]
    assert len(mounts) == 3
    assert all(item["read_only"] and not item["bind"]["create_host_path"] for item in mounts)
    assert all("/dev/null" in item["source"] for item in mounts)


def test_menu_ids_are_wired_only_to_the_services_that_route_them():
    services = yaml.safe_load((ROOT / "infra/gce/docker-compose.production.yml").read_text())[
        "services"
    ]

    assert "LINE_RICH_MENU_ADOPTION_HUB_ID" in services["api"]["environment"]
    assert "LINE_RICH_MENU_ADOPTION_HUB_ID" not in services["worker"]["environment"]
    for name in ("celery-worker", "celery-beat", "web"):
        assert not any(
            key.startswith("LINE_RICH_MENU_") or key.startswith("LINE_ROLE_MENU_")
            for key in services[name]["environment"]
        )


def test_preflight_verifies_actual_candidate_before_runtime_stop():
    preflight = (ROOT / "infra/gce/scripts/production-preflight.sh").read_text()
    deploy = (ROOT / "infra/gce/scripts/deploy-release.sh").read_text()
    assert 'export LINE_ROLE_MENU_RELEASE_MANIFEST="$ROOT_DIR/release-manifest.json"' in preflight
    assert 'services[service]["image"] != entry["repository"]' in preflight
    assert "inconsistent menu scope configuration" in preflight
    assert "validate_runtime_safety" in preflight
    assert deploy.index("checkpoint_stage preflight") < deploy.index(
        "checkpoint_stage runtime_stop"
    )
    assert deploy.index("production-preflight.sh") < deploy.index("systemctl stop strayhub.service")
    assert "sync_line_role_menus" not in deploy


@pytest.mark.parametrize("fault", [None, "scope", "image"])
def test_execute_actual_preflight_rendered_boundary_check(tmp_path, fault):
    script = (ROOT / "infra/gce/scripts/production-preflight.sh").read_text()
    program = re.search(r"config --format json \| python3 -c '\n(.*?)\n'", script, re.S).group(1)
    env = {
        "LINE_ROLE_MENU_FEATURES_ENABLED": "true",
        "LINE_ROLE_MENU_TEST_ENABLED": "false",
        "LINE_CHANNEL_ID": "1234567890",
        "LINE_CHANNEL_ACCESS_TOKEN": "synthetic-token",
        "CELERY_BROKER_URL": "redis://:synthetic@redis:6379/0",
        "CELERY_AI_ENABLED": "false",
    }
    images = {
        role: {"repository": f"synthetic/{role}", "digest": "sha256:" + "a" * 64}
        for role in ("api", "worker", "web")
    }
    services = {
        name: {"environment": dict(env), "image": "synthetic/" + image + "@sha256:" + "a" * 64}
        for name, image in (
            ("api", "api"),
            ("worker", "worker"),
            ("web", "web"),
            ("celery-worker", "worker"),
            ("celery-beat", "worker"),
        )
    }
    for name in ("api", "celery-worker"):
        services[name]["environment"]["ANIMAL_CONFIRMATION_SECRET"] = "synthetic-signing"
    services["redis"] = {"environment": {"REDIS_PASSWORD": "synthetic"}}
    if fault == "scope":
        services["worker"]["environment"]["LINE_ROLE_MENU_TEST_USER_SHA256"] = "f" * 64
    elif fault == "image":
        services["api"]["image"] = "synthetic/api@sha256:" + "b" * 64
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps({"images": images}))
    result = subprocess.run(
        [sys.executable, "-c", program],
        input=json.dumps({"services": services}),
        capture_output=True,
        text=True,
        timeout=10,
        env={"PATH": os.environ["PATH"], "LINE_ROLE_MENU_RELEASE_MANIFEST": str(manifest)},
    )
    assert result.returncode == (0 if fault is None else 1)
    assert "synthetic-token" not in result.stderr
    if fault:
        assert "FAIL" in result.stderr
