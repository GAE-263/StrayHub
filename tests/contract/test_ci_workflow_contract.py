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
    assert "workflow_call" in ci["on"]

    assert "pull_request" not in release["on"]
    assert release["on"]["push"]["branches"] == ["release"]
    assert "workflow_dispatch" in release["on"]


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


def test_release_workflow_reuses_ci_and_only_publish_builds_images() -> None:
    text = RELEASE_PATH.read_text(encoding="utf-8")
    release = _workflow(RELEASE_PATH)

    assert release["jobs"]["full-quality-gate"]["uses"] == "./.github/workflows/ci.yml"
    assert "verify-release" not in release["jobs"]
    assert release["jobs"]["publish-release"]["needs"] == [
        "full-quality-gate",
        "authorize-manual-write",
    ]

    for job_name, job in release["jobs"].items():
        commands = "\n".join(step.get("run", "") for step in job.get("steps", []))
        if job_name == "publish-release":
            assert "docker build" in commands
        else:
            assert "docker build" not in commands
    assert text.count("docker build") == 1
