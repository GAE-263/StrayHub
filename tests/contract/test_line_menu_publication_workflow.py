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

    assert publish["environment"] == "production-line-publication"
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    assert "inputs.operation == 'publish'" in publish["if"]
    assert "secrets.LINE_CHANNEL_ACCESS_TOKEN" in publish_text
    assert "google-github-actions/auth@v2" in publish_text
    assert "GCP_LINE_MENU_MANIFEST_BUCKET" in publish_text
    assert "GCP_LINE_MENU_PUBLISHER_SERVICE_ACCOUNT" in publish_text


def test_both_jobs_pin_and_revalidate_exact_release_head() -> None:
    _, document = workflow()
    for job_name in ("plan", "publish"):
        job_text = yaml.safe_dump(document["jobs"][job_name])
        assert "ref: ${{ inputs.git_sha }}" in job_text
        assert "^[0-9a-f]{40}$" in job_text
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
    assert "GCP_LINE_MENU_MANIFEST_BUCKET" in publish_text
    assert "actions/upload-artifact@v4" in publish_text
