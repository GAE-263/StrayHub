from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = Path(".github/workflows/line-rich-menu-publish.yml")


def workflow() -> tuple[str, dict]:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    return source, yaml.load(source, Loader=yaml.BaseLoader)


def test_workflow_is_manual_only_and_plan_is_default() -> None:
    _, document = workflow()
    triggers = document["on"]

    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["git_sha"]["required"] == "true"
    assert inputs["operation"]["default"] == "plan"
    assert inputs["operation"]["options"] == ["plan", "publish"]
    assert inputs["line_token_secret_version"]["required"] == "false"
    assert inputs["confirmation"]["required"] == "false"
    assert document["permissions"] == {"contents": "read"}


def test_plan_has_no_environment_credentials_or_network_publication() -> None:
    source, document = workflow()
    plan = document["jobs"]["plan"]
    plan_text = yaml.safe_dump(plan)

    assert "environment" not in plan
    assert "secrets." not in plan_text
    assert "google-github-actions/auth" not in plan_text
    assert "line_menu_publication_gate" not in plan_text
    assert "sync_line_role_menus" in plan_text
    assert "workflow_dispatch" in source


def test_publish_is_protected_and_has_minimal_permissions() -> None:
    _, document = workflow()
    publish = document["jobs"]["publish"]
    publish_text = yaml.safe_dump(publish)

    assert publish["environment"] == "release-publication"
    assert publish["permissions"] == {
        "actions": "read",
        "contents": "read",
        "id-token": "write",
    }
    assert "inputs.operation == 'publish'" in publish["if"]
    assert "secrets.LINE_CHANNEL_ACCESS_TOKEN" not in publish_text
    assert "vars." not in publish_text
    assert "google-github-actions/auth@v2" in publish_text
    assert "line-publication-config.json" in publish_text
    assert "gcloud secrets versions access" in publish_text
    assert "--token-file" in publish_text
    assert "::add-mask::" in publish_text
    assert 'versions access "latest"' not in publish_text
    assert publish_text.index("manual_release_gate line-gate") < publish_text.index(
        "google-github-actions/auth@v2"
    )
    assert publish_text.index("google-github-actions/auth@v2") < publish_text.index(
        "gcloud secrets versions access"
    )
    assert "GITHUB_ENV" not in publish_text
    assert "trap cleanup EXIT" in publish_text
    assert "terminate 143" in publish_text and "TERM" in publish_text
    assert "chmod 0600" in publish_text
    for context in (
        "${{ github.actor }}",
        "${{ github.triggering_actor }}",
        "${{ github.run_attempt }}",
    ):
        assert context in publish_text
    assert publish_text.count("release_head_gate") >= 2
    assert publish_text.index("release_head_gate") < publish_text.index(
        "google-github-actions/auth@v2"
    )
    secret_access = publish_text.index("gcloud secrets versions access")
    publication = publish_text.index("scripts.line_menu_publication_gate")
    assert publish_text.rindex("release_head_gate", 0, secret_access) < secret_access
    assert secret_access < publish_text.rindex("release_head_gate") < publication


def test_both_jobs_pin_and_revalidate_exact_release_head() -> None:
    _, document = workflow()
    for job_name in ("plan", "publish"):
        job_text = yaml.safe_dump(document["jobs"][job_name])
        assert "ref: ${{ inputs.git_sha }}" in job_text
        assert "^[0-9a-f]{40}$" in job_text or "manual_release_gate line-gate" in job_text
        assert "git cat-file -t" in job_text
        assert "refs/remotes/origin/release" in job_text
        assert "git merge-base --is-ancestor" in job_text
        assert "refs/heads/release" in job_text


def test_workflow_cannot_promote_configure_or_deploy() -> None:
    source, _ = workflow()
    forbidden = (
        "pull_request:",
        "push:",
        "schedule:",
        "workflow_run:",
        "repository_dispatch:",
        "contents: write",
        "pull-requests: write",
        "packages: write",
        "deployments: write",
        "gcloud compute ssh",
        "sync-production-config",
        "deploy-release",
        "alembic",
        "setDefaultRichMenu",
        "linkRichMenu",
        "unlinkRichMenu",
        "latest.json",
    )

    for marker in forbidden:
        assert marker not in source


def test_artifact_is_only_a_sanitized_copy_not_authoritative_storage() -> None:
    _, document = workflow()
    publish_text = yaml.safe_dump(document["jobs"]["publish"])

    assert "scripts.line_menu_publication_gate" in publish_text
    assert "steps.config.outputs.bucket" in publish_text
    assert "actions/upload-artifact@v4" in publish_text


def test_resume_is_publish_only_and_fail_closed() -> None:
    source, document = workflow()
    plan_text = yaml.safe_dump(document["jobs"]["plan"])
    publish = document["jobs"]["publish"]
    publish_text = yaml.safe_dump(publish)

    inputs = document["on"]["workflow_dispatch"]["inputs"]
    assert {"resume_run_id", "resume_artifact_sha256"} <= set(inputs)
    assert "line_menu_publication_recovery" not in plan_text
    assert "GITHUB_TOKEN" not in plan_text
    assert "line_menu_publication_recovery" in publish_text
    assert publish["permissions"]["actions"] == "read"
    assert "actions: write" not in source
    assert "if: ${{ always() }}" in source
    assert "line-menu-publication-output/progress.json" in source
    assert "line-menu-publication-output/receipt.json" in source


@pytest.mark.parametrize(
    ("uv_status", "signal", "expected"), [("0", "", 0), ("7", "", 7), ("0", "TERM", 143)]
)
def test_secret_file_is_removed_on_success_failure_and_signal(
    tmp_path: Path, uv_status: str, signal: str, expected: int
) -> None:
    _, document = workflow()
    step = next(
        item
        for item in document["jobs"]["publish"]["steps"]
        if item.get("name") == "Access pinned token, publish, and remove token on every exit"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(
        '#!/bin/bash\nset -eu\nfor arg in "$@"; do\n'
        '  case "$arg" in --out-file=*) f=${arg#--out-file=};; esac\n'
        'done\nprintf synthetic-sensitive-value >"$f"\n',
        encoding="utf-8",
    )
    uv = bin_dir / "uv"
    uv.write_text(
        '#!/bin/bash\nif [[ -n "${UV_SIGNAL:-}" ]]; then\n'
        '  kill -s "$UV_SIGNAL" "$PPID"\n  sleep 1\nfi\n'
        'exit "${UV_STATUS:-0}"\n',
        encoding="utf-8",
    )
    python3 = bin_dir / "python3"
    python3.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    git = bin_dir / "git"
    git.write_text('#!/bin/bash\nprintf "%s\\n" "$INPUT_SHA"\n', encoding="utf-8")
    gcloud.chmod(0o755)
    uv.chmod(0o755)
    python3.chmod(0o755)
    git.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
            "BUCKET": "synthetic-bucket",
            "CONFIG_SHA256": "a" * 64,
            "EXPECTED_BOT": "@synthetic",
            "INPUT_SHA": "b" * 40,
            "PROJECT": "synthetic-project",
            "SECRET_NAME": "synthetic-secret",
            "SECRET_VERSION": "3",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "b" * 40,
            "UV_STATUS": uv_status,
            "UV_SIGNAL": signal,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected
    assert not (tmp_path / "line-publication-token").exists()
    output_lines = (result.stdout + result.stderr).splitlines()
    assert output_lines.count("::add-mask::synthetic-sensitive-value") == 1
    assert all(
        "synthetic-sensitive-value" not in line
        for line in output_lines
        if not line.startswith("::add-mask::")
    )
