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


def compare(reference: dict, candidate: dict, environment: str) -> list[str]:
    errors = []
    expected = reference["services"]
    actual = candidate["services"]
    if set(expected) != set(actual):
        errors.append(f"{environment}: service graph differs")
    for name in sorted(set(expected) & set(actual)):
        for field in PROCESS_FIELDS:
            if expected[name].get(field) != actual[name].get(field):
                errors.append(f"{environment}: {name}.{field} differs")
        if set(expected[name].get("environment", {})) != set(actual[name].get("environment", {})):
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
            if not re.fullmatch(
                r"[^@]+@sha256:[0-9a-f]{64}", actual.get(name, {}).get("image", "")
            ):
                errors.append(f"staging: {name} lacks an exact digest")
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
