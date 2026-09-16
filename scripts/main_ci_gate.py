"""Reuse successful exact-main CI evidence without rerunning the quality suite."""

from __future__ import annotations

import argparse
import json
import re
import subprocess

REPOSITORY = "GAE-263/StrayHub"
WORKFLOW = ".github/workflows/ci.yml"
CHECKS = {"python", "Frontend Quality", "Contracts", "Critical E2E", "GCE Release Static Contracts"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def gh(endpoint: str) -> dict:
    result = subprocess.run(
        ["gh", "api", "--method", "GET", f"repos/{REPOSITORY}/{endpoint}"],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def validate_run(run: dict, workflow: dict, sha: str) -> None:
    require(workflow.get("path") == WORKFLOW, "wrong CI workflow")
    expected = {
        "head_sha": sha,
        "head_branch": "main",
        "event": "push",
        "path": WORKFLOW,
        "status": "completed",
        "conclusion": "success",
        "workflow_id": workflow.get("id"),
    }
    require(all(run.get(k) == v for k, v in expected.items()), "exact main CI has not passed")
    require(
        run.get("repository", {}).get("full_name") == REPOSITORY
        and run.get("head_repository", {}).get("full_name") == REPOSITORY,
        "CI repository mismatch",
    )
    for key in ("id", "run_attempt"):
        require(type(run.get(key)) is int and run[key] > 0, "invalid CI run identity")


def validate_jobs(document: dict, run: dict, sha: str) -> None:
    jobs = document.get("jobs", [])
    require(document.get("total_count") == len(jobs) == len(CHECKS), "incomplete CI job set")
    require({j.get("name") for j in jobs} == CHECKS, "required CI checks differ")
    for job in jobs:
        require(
            job.get("run_id") == run["id"]
            and job.get("run_attempt") == run["run_attempt"]
            and job.get("head_sha") == sha
            and job.get("status") == "completed"
            and job.get("conclusion") == "success",
            "required CI check did not pass in the selected attempt",
        )


def verify(sha: str) -> int:
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "invalid full Git SHA")
    workflow = gh("actions/workflows/ci.yml")
    listing = gh(f"actions/workflows/ci.yml/runs?branch=main&event=push&head_sha={sha}&per_page=1")
    runs = listing.get("workflow_runs", [])
    require(len(runs) == 1, "no exact main push CI evidence")
    # Select the newest run, never search backwards for an older passing result.
    run = runs[0]
    validate_run(run, workflow, sha)
    jobs = gh(f"actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100")
    validate_jobs(jobs, run, sha)
    # Refuse a concurrent rerun/changed conclusion between metadata and job reads.
    latest = gh(f"actions/runs/{run['id']}")
    validate_run(latest, workflow, sha)
    require(latest["run_attempt"] == run["run_attempt"], "CI attempt changed during validation")
    print(f"Exact main CI PASS: run={run['id']} attempt={run['run_attempt']} sha={sha}")
    return run["id"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-sha", required=True)
    args = parser.parse_args()
    try:
        verify(args.git_sha)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        # Never echo raw transport errors or authentication material.
        parser.exit(1, "Exact main CI evidence unavailable or invalid; refusing credentials.\n")


if __name__ == "__main__":
    main()
