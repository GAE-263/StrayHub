"""Manual authorization for reviewed online plans; no cloud access."""

import argparse
import os
import re
import subprocess

from scripts.manual_release_gate import GateError, validate_manual_run_identity
from scripts.release_head_gate import read_current_release_head


def authorize(operation: str, plan_sha256: str, git_sha: str, confirmation: str) -> None:
    if operation not in {"config-sync", "menu-switch", "menu-restore", "reload-config"}:
        raise GateError("operation")
    validate_manual_run_identity(
        os.environ.get("GITHUB_ACTOR", ""),
        os.environ.get("GITHUB_TRIGGERING_ACTOR", ""),
        os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    )
    if (
        os.environ.get("GITHUB_REPOSITORY") != "GAE-263/StrayHub"
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("GITHUB_REF") != "refs/heads/release"
        or not re.fullmatch(r"[0-9a-f]{64}", plan_sha256)
        or not re.fullmatch(r"[0-9a-f]{40}", git_sha)
        or confirmation != f"LINE ONLINE {operation} {git_sha} {plan_sha256}"
    ):
        raise GateError("manual_plan_identity")
    checkout = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
    ).stdout.strip()
    read_current_release_head(git_sha, os.environ.get("GITHUB_SHA", ""), checkout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    try:
        authorize(args.operation, args.plan_sha256, args.git_sha, args.confirmation)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
        parser.exit(1, "manual_online_gate_denied\n")


if __name__ == "__main__":
    main()
