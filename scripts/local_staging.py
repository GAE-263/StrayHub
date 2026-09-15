"""Manually rehearse an immutable release on an explicitly selected local Docker context.

This produces runtime-only evidence, never a production promotion approval.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib.util
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from scripts.check_runtime_parity import APPLICATION_IMAGES, ROOT, compare

OVERLAY = ROOT / "infra/gce/docker-compose.staging.yml"
PROJECT = "strayhub-staging"


def run(args: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(args, env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        # Docker diagnostics and application output may contain secrets.
        raise ValueError("Command failed; no runtime receipt issued (diagnostics suppressed)")
    return result.stdout


def validate_context(context: dict) -> None:
    host = context["Endpoints"]["docker"]["Host"]
    if not host.startswith("unix://"):
        raise ValueError("Staging requires a local Unix-socket Docker context, not TCP/SSH")


def validate_model(model: dict) -> None:
    if model["name"] != PROJECT:
        raise ValueError("Unexpected staging project")
    network = model["networks"]["strayhub_runtime"]
    if not network.get("internal"):
        raise ValueError("Staging outbound network must be disabled")
    for kind in ("networks", "volumes"):
        for item in model.get(kind, {}).values():
            if item.get("external") or not item.get("name", "").startswith(PROJECT + "_"):
                raise ValueError("Staging resources must be project-isolated")
    for service, config in model["services"].items():
        if config.get("build") or config.get("privileged") or config.get("network_mode"):
            raise ValueError("Unsafe staging service configuration")
        if service in APPLICATION_IMAGES and config.get("platform") != "linux/amd64":
            raise ValueError("Release application images must use linux/amd64")
        for port in config.get("ports", []):
            if port.get("host_ip") != "127.0.0.1":
                raise ValueError("Staging ports must bind loopback")
        values = config.get("environment", {})
        if any("REPLACE" in str(value) for value in values.values()):
            raise ValueError("Replace staging template placeholders before deployment")
        if "APP_ENV" in values and values["APP_ENV"] != "local":
            raise ValueError("Local staging requires APP_ENV=local")
        for key, host in (
            ("DATABASE_URL", "postgres"),
            ("CELERY_BROKER_URL", "redis"),
            ("MINIO_ENDPOINT", "minio"),
        ):
            if key in values and urlsplit(values[key]).hostname != host:
                raise ValueError(f"{key} must target the isolated Compose service")
        if "AI_PROVIDER" in values and values["AI_PROVIDER"] != "mock":
            raise ValueError("Local staging requires mock AI")
        if (
            "PII_ENCRYPTION_PROVIDER" in values
            and values["PII_ENCRYPTION_PROVIDER"] != "local-aes-gcm"
        ):
            raise ValueError("Local staging requires local PII encryption")
    api_values = model["services"]["api"]["environment"]
    try:
        key = base64.b64decode(api_values.get("PII_LOCAL_KEY_BASE64", ""), validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Staging AES key must be base64-encoded 32 bytes") from None
    if len(key) != 32 or str(api_values.get("PII_ALLOW_LOCAL_PROVIDER")).lower() != "true":
        raise ValueError("Staging requires enabled local AES encryption with a 32-byte key")


def verify_container(container: dict, service: str, expected_image: str | None) -> None:
    state = container["State"]
    if state["Status"] != "running":
        raise ValueError(f"{service} is not running")
    if state.get("Health", {}).get("Status", "healthy") != "healthy":
        raise ValueError(f"{service} is not healthy")
    if expected_image and container["Config"]["Image"] != expected_image:
        raise ValueError(f"{service} image identity mismatch")


def deploy(args: argparse.Namespace) -> None:
    # Prevent inherited production interpolation/Compose/Docker overrides.
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "DOCKER_CONFIG", "TMPDIR"}
    }
    docker = ["docker", "--context", args.context]
    contexts = json.loads(run(docker + ["context", "inspect", args.context], env))
    validate_context(contexts[0])
    spec = importlib.util.spec_from_file_location(
        "release_manifest", ROOT / "infra/gce/scripts/release-manifest.py"
    )
    assert spec and spec.loader
    manifest_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manifest_tool)
    manifest_tool.parse_image_reference(args.artifact)
    if not args.confirm_local_secrets:
        raise ValueError("Confirm dedicated local secrets and synthetic data before deployment")
    if not args.env_file.is_file() or args.env_file.stat().st_mode & 0o077:
        raise ValueError("Local env file must exist with mode 0600")
    args.work_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    artifact_dir = args.work_dir / "artifact"
    artifact_dir.mkdir()
    print("Fetching immutable release artifact", flush=True)
    run(docker + ["pull", "--platform", "linux/amd64", args.artifact], env)
    container = run(
        docker + ["create", args.artifact, "/release-artifact-not-executed"], env
    ).strip()
    try:
        for name in (
            "release-manifest.json",
            "deployment-bundle.tar",
            "checksums.sha256",
            "release-identity.json",
        ):
            run(docker + ["cp", f"{container}:/{name}", str(artifact_dir / name)], env)
    finally:
        run(docker + ["rm", container], env)
    manifest = manifest_tool.validate_artifact(artifact_dir)
    identity = json.loads((artifact_dir / "release-identity.json").read_text())
    images = {
        key: value["repository"] + "@" + value["digest"]
        for key, value in manifest["images"].items()
    }
    expected = {
        "git_sha": manifest["git_sha"],
        "release_id": manifest["release_id"],
        "images": images,
        "manifest_sha256": manifest_tool.sha256_file(artifact_dir / "release-manifest.json"),
        "bundle_sha256": manifest_tool.sha256_file(artifact_dir / "deployment-bundle.tar"),
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("Release identity mismatch")
    release = args.work_dir / "release"
    manifest_tool.extract_artifact(artifact_dir, release)
    env.update({f"STRAYHUB_{name.upper()}_IMAGE": value for name, value in images.items()})
    base = [
        *docker,
        "compose",
        "--env-file",
        str(args.env_file.resolve()),
        "-f",
        str(release / "infra/gce/docker-compose.production.yml"),
    ]
    compose = base + ["-f", str(OVERLAY), "--project-name", PROJECT]
    reference = json.loads(run(base + ["--profile", "*", "config", "--format", "json"], env))
    model = json.loads(run(compose + ["--profile", "*", "config", "--format", "json"], env))
    validate_model(model)
    if compare(reference, model, "staging"):
        raise ValueError("Selected artifact does not match the local staging runtime contract")
    print("Pulling release images; migrating isolated database", flush=True)
    run(compose + ["--profile", "*", "pull"], env)
    # Stop only this project's application processes before migrating persistent local data.
    run(compose + ["stop", "api", "web", "worker", "celery-worker", "celery-beat"], env)
    run(
        compose
        + [
            "up",
            "-d",
            "--no-build",
            "--wait",
            "--wait-timeout",
            "180",
            "postgres",
            "minio",
            "redis",
        ],
        env,
    )
    run(compose + ["run", "--rm", "--no-deps", "migration"], env)
    print("Starting runtime and waiting for health checks", flush=True)
    run(compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "300"], env)
    for service in model["services"]:
        if service in {"migration", "minio-bootstrap"}:
            continue
        ids = run(compose + ["ps", "-q", service], env).split()
        if len(ids) != 1:
            raise ValueError(f"Expected exactly one {service} container")
        item = json.loads(run(docker + ["inspect", ids[0]], env))[0]
        image = images.get(APPLICATION_IMAGES.get(service, ""))
        verify_container(item, service, image)
    receipt = {
        **expected,
        "artifact_image": args.artifact,
        "scope": "local-docker-runtime-only",
        "production_promotion_approved": False,
        "runtime": "PASS",
        "authenticated_e2e": "NOT_RUN",
        "cloud_checks": "NOT_RUN",
        "overlay_sha256": hashlib.sha256(OVERLAY.read_bytes()).hexdigest(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    (args.work_dir / "runtime-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Local runtime PASS. E2E/cloud acceptance pending; production promotion NOT approved.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact", required=True, help="Trusted release artifact repository@sha256:digest"
    )
    parser.add_argument("--context", required=True, help="Explicit local Docker context")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument(
        "--work-dir", type=Path, required=True, help="New directory for this attempt"
    )
    parser.add_argument("--confirm-local-secrets", action="store_true")
    try:
        deploy(parser.parse_args())
    except (ValueError, OSError, KeyError) as exc:
        print(f"Local staging failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
