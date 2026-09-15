from __future__ import annotations

import copy

import pytest
from scripts.local_staging import validate_context, validate_model, verify_container, verify_e2e


def model():
    return {
        "name": "strayhub-staging",
        "networks": {
            "strayhub_runtime": {"name": "strayhub-staging_runtime", "internal": True},
            "staging_ingress": {"name": "strayhub-staging_ingress"},
        },
        "volumes": {"data": {"name": "strayhub-staging_data"}},
        "services": {
            "api": {
                "platform": "linux/amd64",
                "environment": {
                    "APP_ENV": "local",
                    "DATABASE_URL": "postgresql://user@postgres/db",
                    "AI_PROVIDER": "mock",
                    "PII_ENCRYPTION_PROVIDER": "local-aes-gcm",
                    "PII_ALLOW_LOCAL_PROVIDER": "true",
                    "PII_LOCAL_KEY_BASE64": "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=",
                },
                "image": "example.invalid/api@sha256:" + "a" * 64,
            },
            "web": {"platform": "linux/amd64"},
            "staging-edge": {
                "image": "example.invalid/api@sha256:" + "a" * 64,
                "networks": {"strayhub_runtime": {}, "staging_ingress": {}},
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "command": ["python", "-m", "scripts.local_staging_proxy"],
                "ports": [
                    {"host_ip": "127.0.0.1", "target": 8081, "published": "18082"},
                    {"host_ip": "127.0.0.1", "target": 8080, "published": "13002"},
                ],
            },
        },
    }


def test_local_model_allowed():
    validate_model(model())


@pytest.mark.parametrize(
    "field,value",
    [
        ("APP_ENV", "production"),
        ("DATABASE_URL", "postgresql://user@production/db"),
        ("AI_PROVIDER", "gemini"),
        ("PII_ENCRYPTION_PROVIDER", "gcp-kms"),
    ],
)
def test_remote_or_production_config_rejected(field, value):
    candidate = model()
    candidate["services"]["api"]["environment"][field] = value
    with pytest.raises(ValueError):
        validate_model(candidate)


@pytest.mark.parametrize(
    "mutation", ["network", "volume", "platform", "port", "build", "edge_secret", "api_port"]
)
def test_isolation_required(mutation):
    candidate = copy.deepcopy(model())
    if mutation == "network":
        candidate["networks"]["strayhub_runtime"]["internal"] = False
    elif mutation == "volume":
        candidate["volumes"]["data"]["name"] = "strayhub-production_data"
    elif mutation == "platform":
        candidate["services"]["api"]["platform"] = "linux/arm64"
    elif mutation == "port":
        candidate["services"]["staging-edge"]["ports"][0]["host_ip"] = "0.0.0.0"
    elif mutation == "edge_secret":
        candidate["services"]["staging-edge"]["environment"] = {"SECRET": "unsafe"}
    elif mutation == "api_port":
        candidate["services"]["api"]["ports"] = [{"host_ip": "127.0.0.1"}]
    else:
        candidate["services"]["api"]["build"] = {"context": "."}
    with pytest.raises(ValueError):
        validate_model(candidate)


@pytest.mark.parametrize("host", ["ssh://production", "tcp://127.0.0.1:2375"])
def test_remote_context_rejected(host):
    with pytest.raises(ValueError):
        validate_context({"Endpoints": {"docker": {"Host": host}}})


def test_local_context_allowed():
    validate_context({"Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}}})


@pytest.mark.parametrize(
    "state,image",
    [
        ({"Status": "exited"}, "expected"),
        ({"Status": "running", "Health": {"Status": "unhealthy"}}, "expected"),
        ({"Status": "running"}, "wrong"),
    ],
)
def test_runtime_failure_rejected(state, image):
    with pytest.raises(ValueError):
        verify_container({"State": state, "Config": {"Image": image}}, "api", "expected")


def test_live_acceptance_requires_rls_and_cross_shelter_passes():
    result = {
        key: "PASS"
        for key in (
            "valid_login",
            "invalid_auth",
            "authenticated_api",
            "tenant_a_positive",
            "tenant_b_negative",
            "volunteer_grant",
            "qr_first",
            "care_report",
            "cross_shelter_denial",
        )
    }
    result.update(
        runtime_role="staging_app",
        runtime_bypassrls=False,
        runtime_superuser=False,
        rls_table_count=48,
    )
    verify_e2e(result, "staging_app")
    result["runtime_bypassrls"] = True
    with pytest.raises(ValueError):
        verify_e2e(result, "staging_app")


@pytest.mark.parametrize("fail_step", [None, "migration", "up", "inspect"])
def test_deployment_receipt_is_fail_closed(tmp_path, monkeypatch, fail_step):
    import argparse
    import json
    from types import SimpleNamespace

    from scripts import local_staging as staging

    digest = "sha256:" + "a" * 64
    images = {
        key: {"repository": f"example.invalid/{key}", "digest": digest}
        for key in ("api", "worker", "web")
    }
    manifest = {
        "git_sha": "b" * 40,
        "release_id": "synthetic",
        "images": images,
        "migration_revision": "0056_synthetic",
    }
    identity = {
        **manifest,
        "images": {key: item["repository"] + "@" + digest for key, item in images.items()},
        "manifest_sha256": "checksum",
        "bundle_sha256": "checksum",
    }
    helper = SimpleNamespace(
        parse_image_reference=lambda value: None,
        validate_artifact=lambda path: manifest,
        sha256_file=lambda path: "checksum",
        extract_artifact=lambda source, target: None,
    )
    monkeypatch.setattr(staging.importlib.util, "module_from_spec", lambda spec: helper)
    monkeypatch.setattr(
        staging.importlib.util,
        "spec_from_file_location",
        lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda m: None)),
    )
    # Manifest/extraction and Compose comparison have separate real contract tests.
    monkeypatch.setattr(staging, "compare", lambda *args: [])
    calls = []

    def fake_run(command, env):
        calls.append(command)
        if "context" in command and "inspect" in command:
            return json.dumps([{"Endpoints": {"docker": {"Host": "unix:///local.sock"}}}])
        if "create" in command:
            return "artifact-container"
        if "cp" in command and command[-1].endswith("release-identity.json"):
            from pathlib import Path

            Path(command[-1]).write_text(json.dumps(identity))
        if "config" in command:
            return json.dumps(model())
        if fail_step == "migration" and "run" in command:
            raise ValueError("migration failed")
        if fail_step == "up" and "up" in command:
            raise ValueError("startup failed")
        if "ps" in command:
            return f"{command[-1]}-container"
        if "SELECT version_num FROM alembic_version" in command:
            return "0056_synthetic\n"
        if "scripts.verify_acceptance_live" in command[-1]:
            return json.dumps(
                {
                    **{
                        key: "PASS"
                        for key in (
                            "valid_login",
                            "invalid_auth",
                            "authenticated_api",
                            "tenant_a_positive",
                            "tenant_b_negative",
                            "volunteer_grant",
                            "qr_first",
                            "care_report",
                            "cross_shelter_denial",
                        )
                    },
                    "runtime_role": "staging_app",
                    "runtime_bypassrls": False,
                    "runtime_superuser": False,
                    "rls_table_count": 48,
                }
            )
        if "inspect" in command:
            if fail_step == "inspect":
                raise ValueError("inspection failed")
            service = command[-1].removesuffix("-container")
            image_key = "api" if service == "staging-edge" else service
            return json.dumps(
                [
                    {
                        "State": {"Status": "running", "Health": {"Status": "healthy"}},
                        "Config": {"Image": identity["images"].get(image_key, "infrastructure")},
                    }
                ]
            )
        return ""

    monkeypatch.setattr(staging, "run", fake_run)
    monkeypatch.setattr(staging, "probe_loopback", lambda url: None)
    env_file = tmp_path / "local.env"
    env_file.write_text(
        "POSTGRES_USER=staging_migration\n"
        "POSTGRES_DB=strayhub_staging\n"
        "DATABASE_URL=postgresql+asyncpg://staging_app:password@postgres/db\n"
        "DATABASE_MIGRATION_URL=postgresql+asyncpg://staging_migration:password@postgres/db\n"
    )
    env_file.chmod(0o600)
    work = tmp_path / "attempt"
    args = argparse.Namespace(
        context="local",
        artifact="example.invalid/release@" + digest,
        env_file=env_file,
        work_dir=work,
        confirm_local_secrets=True,
    )
    if fail_step:
        with pytest.raises(ValueError):
            staging.deploy(args)
        assert not (work / "staging-receipt.json").exists()
    else:
        staging.deploy(args)
        receipt = json.loads((work / "staging-receipt.json").read_text())
        assert receipt["artifact_image"] == args.artifact
        assert receipt["production_promotion_approved"] is False
        assert receipt["authenticated_e2e"]["status"] == "PASS"
        assert receipt["migration_revision"]["actual"] == "0056_synthetic"
        assert all("--no-build" in call for call in calls if "up" in call)
        assert not any("build" in call for call in calls)
