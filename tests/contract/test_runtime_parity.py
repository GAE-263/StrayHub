from __future__ import annotations

import copy

import pytest
from scripts.check_runtime_parity import ROOT, compare, render


@pytest.fixture(scope="module")
def models():
    from unittest.mock import patch

    images = {
        f"STRAYHUB_{service.upper()}_IMAGE": f"example.invalid/strayhub-{service}@sha256:{'a' * 64}"
        for service in ("api", "worker", "web")
    }
    with patch.dict("os.environ", images):
        return {
            name: render(ROOT / "infra/gce/.env.production.example", name)
            for name in ("production", "local", "staging")
        }


@pytest.mark.parametrize("environment", ["local", "staging"])
def test_rendered_environment_has_same_runtime_contract(models, environment):
    assert compare(models["production"], models[environment], environment) == []


@pytest.mark.parametrize("field", ["command", "depends_on", "healthcheck", "environment"])
def test_runtime_drift_is_rejected(models, field):
    changed = copy.deepcopy(models["staging"])
    changed["services"]["api"][field] = {}
    assert compare(models["production"], changed, "staging")


@pytest.mark.parametrize("kind", ["volumes", "networks"])
def test_shared_production_resources_are_rejected(models, kind):
    changed = copy.deepcopy(models["staging"])
    changed[kind] = copy.deepcopy(models["production"][kind])
    assert compare(models["production"], changed, "staging")


def test_mutable_image_and_build_are_rejected(models):
    changed = copy.deepcopy(models["staging"])
    changed["services"]["api"]["image"] = "example.invalid/api:latest"
    changed["services"]["api"]["build"] = {"context": "."}
    errors = compare(models["production"], changed, "staging")
    assert "staging: api permits a build" in errors
    assert "staging: api lacks an exact digest" in errors


def test_public_staging_port_is_rejected(models):
    changed = copy.deepcopy(models["staging"])
    changed["services"]["api"]["ports"][0]["host_ip"] = "0.0.0.0"
    assert "staging: api publishes outside loopback" in compare(
        models["production"], changed, "staging"
    )
