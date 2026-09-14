from __future__ import annotations

from pathlib import Path

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
