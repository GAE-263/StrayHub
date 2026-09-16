from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_PATH = ROOT / ".github/workflows/ci.yml"
RELEASE_PATH = ROOT / ".github/workflows/gce-release.yml"


def _workflow(path: Path) -> dict[str, object]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_primary_ci_is_the_only_pr_and_main_quality_workflow() -> None:
    ci = _workflow(CI_PATH)
    release = _workflow(RELEASE_PATH)

    assert "pull_request" in ci["on"]
    assert ci["on"]["push"]["branches"] == ["main"]
    assert "workflow_call" not in ci["on"]

    assert "pull_request" not in release["on"]
    assert "push" not in release["on"]
    assert "workflow_dispatch" in release["on"]
    assert "schema_compatibility" not in release["on"]["workflow_dispatch"]["inputs"]


def test_primary_ci_owns_release_static_contracts_without_cloud_credentials() -> None:
    text = CI_PATH.read_text(encoding="utf-8")
    ci = _workflow(CI_PATH)
    python_steps = "\n".join(step.get("run", "") for step in ci["jobs"]["python"]["steps"])
    release_job = ci["jobs"]["release-static"]
    release_steps = "\n".join(step.get("run", "") for step in release_job["steps"])

    for required in (
        "shellcheck",
        "infra/gce/scripts/preflight.sh",
        "docker compose",
        "terraform fmt -check",
        "terraform validate",
        "Repository-native secret scan",
    ):
        assert required in text
    assert "uv run ruff check ." in python_steps
    assert "uv run ruff format --check ." in python_steps
    assert "uv run pytest" in python_steps
    assert "id-token: write" not in text
    assert "google-github-actions/auth" not in text
    assert "gcloud " not in release_steps


def test_release_workflow_reuses_ci_evidence_and_only_main_builds_images() -> None:
    text = RELEASE_PATH.read_text(encoding="utf-8")
    release = _workflow(RELEASE_PATH)

    assert "full-quality-gate" not in release["jobs"]
    assert "verify-release" not in release["jobs"]
    assert release["jobs"]["publish-release"]["needs"] == "authorize-manual-write"
    for name in ("publish-release", "deploy-production"):
        job = release["jobs"][name]
        auth = next(i for i, s in enumerate(job["steps"]) if "auth@" in s.get("uses", ""))
        assert any("scripts.main_ci_gate" in s.get("run", "") for s in job["steps"][:auth])
        assert job["permissions"]["actions"] == "read"

    for job in release["jobs"].values():
        commands = "\n".join(step.get("run", "") for step in job.get("steps", []))
        assert "docker build" not in commands
    assert "build-immutable-release.sh" in text
    assert "--reuse-only" in text
