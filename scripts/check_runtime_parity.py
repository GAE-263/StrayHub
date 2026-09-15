"""Compare rendered Compose models without printing environment secrets.

Production Compose is the canonical service definition. Environment overlays may
change resource limits, host ports, secret sources and build policy, not processes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "infra/gce/docker-compose.production.yml"
OVERRIDES = {
    "local": ROOT / "infra/local/docker-compose.runtime.yml",
    "staging": ROOT / "infra/gce/docker-compose.staging.yml",
}
PROCESS_FIELDS = (
    "command",
    "entrypoint",
    "depends_on",
    "healthcheck",
    "profiles",
    "networks",
)
APPLICATION_IMAGES = {
    "api": "api",
    "migration": "api",
    "worker": "worker",
    "celery-worker": "worker",
    "celery-beat": "worker",
    "web": "web",
}
STAGING_EDGE_COMMAND = ["python", "-m", "scripts.local_staging_proxy"]
STAGING_EDGE_PORTS = {("127.0.0.1", 8081, "18082"), ("127.0.0.1", 8080, "13002")}


def compare(reference: dict, candidate: dict, environment: str) -> list[str]:
    errors = []
    expected = reference["services"]
    actual = candidate["services"]
    allowed_extra = {"staging-edge"} if environment == "staging" else set()
    if set(actual) - allowed_extra != set(expected):
        errors.append(f"{environment}: service graph differs")
    for name in sorted(set(expected) & set(actual)):
        for field in PROCESS_FIELDS:
            if expected[name].get(field) != actual[name].get(field):
                errors.append(f"{environment}: {name}.{field} differs")
        expected_keys = set(expected[name].get("environment", {}))
        actual_keys = set(actual[name].get("environment", {}))
        # Local Docker uses dedicated AES encryption instead of cloud KMS.
        if environment == "staging" and name == "api":
            expected_keys |= {"PII_ALLOW_LOCAL_PROVIDER", "PII_LOCAL_KEY_BASE64"}
        if expected_keys != actual_keys:
            errors.append(f"{environment}: {name} environment contract differs")
        if expected[name].get("volumes") != actual[name].get("volumes"):
            errors.append(f"{environment}: {name} storage mount contract differs")
        if expected[name].get("secrets") != actual[name].get("secrets"):
            errors.append(f"{environment}: {name} secret mount contract differs")
        if environment == "staging" and actual[name].get("build"):
            errors.append(f"staging: {name} permits a build")
        if expected[name].get("image") != actual[name].get("image"):
            errors.append(f"{environment}: {name} image differs")
        if environment in OVERRIDES:
            for port in actual[name].get("ports", []):
                if port.get("host_ip") != "127.0.0.1":
                    errors.append(f"{environment}: {name} publishes outside loopback")
    if environment == "staging":
        import re

        for name in APPLICATION_IMAGES:
            if actual.get(name, {}).get("platform") != "linux/amd64":
                errors.append(f"staging: {name} must run the linux/amd64 release")
            if not re.fullmatch(
                r"[^@]+@sha256:[0-9a-f]{64}", actual.get(name, {}).get("image", "")
            ):
                errors.append(f"staging: {name} lacks an exact digest")
        if not candidate.get("networks", {}).get("strayhub_runtime", {}).get("internal"):
            errors.append("staging: outbound network is not isolated")
        edge = actual.get("staging-edge", {})
        if edge.get("image") != actual.get("api", {}).get("image"):
            errors.append("staging: edge must use the immutable API release image")
        if set(edge.get("networks", {})) != {"strayhub_runtime", "staging_ingress"}:
            errors.append("staging: edge network boundary differs")
        if candidate.get("networks", {}).get("staging_ingress", {}).get("internal"):
            errors.append("staging: ingress network cannot publish loopback ports")
        edge_secret_mounts = edge["secrets"] if "secrets" in edge else None
        if edge.get("environment") or edge_secret_mounts or edge.get("volumes"):
            errors.append("staging: edge must not receive configuration or secrets")
        if (
            not edge.get("read_only")
            or edge.get("cap_drop") != ["ALL"]
            or edge.get("security_opt") != ["no-new-privileges:true"]
            or edge.get("command") != STAGING_EDGE_COMMAND
        ):
            errors.append("staging: edge sandbox is incomplete")
        ports = {
            (port.get("host_ip"), port.get("target"), str(port.get("published")))
            for port in edge.get("ports", [])
        }
        if ports != STAGING_EDGE_PORTS:
            errors.append("staging: edge port contract differs")
        for port in edge.get("ports", []):
            if port.get("host_ip") != "127.0.0.1":
                errors.append("staging: staging-edge publishes outside loopback")
        for name in ("api", "web"):
            if actual.get(name, {}).get("ports"):
                errors.append(f"staging: {name} must not publish ports directly")
    # Compose resolves unnamed resources under the project name; explicit shared
    # names or external resources would silently bypass environment isolation.
    if candidate.get("name") == reference.get("name"):
        errors.append(f"{environment}: project name is not isolated")
    for kind in ("volumes", "networks"):
        reference_names = {item.get("name") for item in reference.get(kind, {}).values()}
        for item in candidate.get(kind, {}).values():
            if item.get("external") or item.get("name") in reference_names:
                errors.append(f"{environment}: shared {kind} resource")
    return errors


def render(env_file: Path, environment: str) -> dict:
    args = ["docker", "compose", "--profile", "*", "--env-file", str(env_file), "-f", str(BASE)]
    if environment in OVERRIDES:
        args += ["-f", str(OVERRIDES[environment])]
    result = subprocess.run(args + ["config", "--format", "json"], capture_output=True, check=False)
    if result.returncode:
        # Compose diagnostics can include interpolated configuration. Do not echo them.
        raise ValueError(f"{environment}: Compose rendering failed; check required configuration")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        reference = render(args.env_file, "production")
        errors = [
            error
            for environment in OVERRIDES
            for error in compare(reference, render(args.env_file, environment), environment)
        ]
    except (ValueError, OSError) as exc:
        print(f"Runtime parity FAIL: {exc}")
        return 1
    if errors:
        print("\n".join(errors))
        return 1
    print("Runtime parity PASS: Local / Staging / Production share the same service contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
