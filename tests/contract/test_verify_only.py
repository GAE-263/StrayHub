"""Independent verification is target-bound and cannot enter deployment paths."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = yaml.load(
    (ROOT / ".github/workflows/gce-release.yml").read_text(), Loader=yaml.BaseLoader
)
JOB = DOCUMENT["jobs"]["verify-production"]
SHA = "a" * 40
RELEASE = "20260915T143105Z-" + "a" * 12


def step(name: str) -> dict:
    return next(s for s in JOB["steps"] if s.get("name") == name)


def test_verify_only_has_no_build_or_write_path() -> None:
    assert "!cancelled()" in JOB["if"]
    assert "inputs.operation == 'verify'" in JOB["if"]
    assert "needs.deploy-production.result == 'success'" in JOB["if"]
    for name in ("authorize-manual-write", "publish-release", "deploy-production"):
        assert "inputs.operation == 'verify'" not in DOCUMENT["jobs"][name]["if"]
        assert "inputs.operation == 'deploy'" in DOCUMENT["jobs"][name]["if"] or (
            "inputs.operation == 'publish'" in DOCUMENT["jobs"][name]["if"]
        )
    assert "full-quality-gate" not in DOCUMENT["jobs"]
    assert "scripts.main_ci_gate" not in str(JOB)
    assert JOB["steps"][0]["with"]["ref"] == "${{ github.sha }}"
    text = str(JOB)
    for forbidden in ("docker build", "docker push", "deploy-release-ci.sh", "alembic upgrade"):
        assert forbidden not in text
    for name in (
        "Bind verification to the successful deployment in this run",
        "Record whether release advanced after the completed deployment",
        "Record deployed release status",
    ):
        assert step(name)["if"] == "${{ inputs.operation == 'deploy' }}"
    auth_index = next(i for i, s in enumerate(JOB["steps"]) if "auth@" in s.get("uses", ""))
    assert JOB["steps"].index(step("Validate exact verification target before credentials")) < (
        auth_index
    )


@pytest.mark.parametrize(
    ("sha", "confirmation", "valid"),
    [
        (SHA, f"VERIFY PRODUCTION {SHA} {RELEASE}", True),
        (SHA, "", False),
        (SHA, f"VERIFY PRODUCTION {SHA} {RELEASE}; true", False),
        (SHA, f"VERIFY PRODUCTION {SHA} 20260915T143105Z-bbbbbbbbbbbb", False),
        ("$(touch bad)", f"VERIFY PRODUCTION {SHA} {RELEASE}", False),
        (SHA, f"VERIFY PRODUCTION {'b' * 40} {RELEASE}", False),
    ],
)
def test_target_gate(tmp_path: Path, sha: str, confirmation: str, valid: bool) -> None:
    # Mock only identity CLI and git; execute the actual workflow target-validation shell.
    for name, body in (("python3", "exit 0"), ("git", 'echo "$GITHUB_SHA"')):
        command = tmp_path / name
        command.write_text(f"#!/bin/bash\n{body}\n")
        command.chmod(0o700)
    result = subprocess.run(
        ["bash", "-e", "-c", step("Validate exact verification target before credentials")["run"]],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "OPERATION": "verify",
            "INPUT_SHA": sha,
            "CONFIRMATION": confirmation,
            "GITHUB_SHA": "b" * 40,
            "GITHUB_OUTPUT": str(tmp_path / "output"),
        },
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == valid
    if valid:
        assert (tmp_path / "output").read_text() == f"release_id={RELEASE}\n"


@pytest.mark.parametrize(
    ("status", "classification"),
    [
        (0, "PASS"),
        (40, "REMOTE_VERIFICATION_FAILURE"),
        (255, "SSH_TRANSPORT_FAILURE"),
        (1, "TRANSPORT_OR_EXECUTION_FAILURE"),
    ],
)
def test_runtime_failure_classification(tmp_path: Path, status: int, classification: str) -> None:
    command = tmp_path / "gcloud"
    command.write_text('#!/bin/bash\nexit "$STATUS"\n')
    command.chmod(0o700)
    result = subprocess.run(
        ["bash", "-e", "-c", step("Verify exact receipt and runtime over IAP")["run"]],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "STATUS": str(status),
            "INPUT_SHA": SHA,
            "RELEASE_ID": RELEASE,
            "GITHUB_OUTPUT": str(tmp_path / "output"),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == status
    assert (tmp_path / "output").read_text() == f"classification={classification}\n"
    assert step("Record independent verification outcomes")["if"] == "${{ always() }}"
