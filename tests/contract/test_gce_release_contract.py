from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "infra/gce/scripts/release-manifest.py"
SPEC = importlib.util.spec_from_file_location("strayhub_release_manifest", TOOL_PATH)
assert SPEC and SPEC.loader
release_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_manifest)

GIT_SHA = "a" * 40
DIGESTS = {
    "api": f"asia-east1-docker.pkg.dev/project/strayhub/api@sha256:{'1' * 64}",
    "worker": f"asia-east1-docker.pkg.dev/project/strayhub/worker@sha256:{'2' * 64}",
    "web": f"asia-east1-docker.pkg.dev/project/strayhub/web@sha256:{'3' * 64}",
}
RELEASE_ID = f"20260831T120000Z-{GIT_SHA[:12]}"
PREVIOUS_RELEASE = f"20260830T120000Z-{'b' * 12}"


@pytest.mark.parametrize("fetch_status", [0, 1])
def test_candidate_secrets_are_materialized_without_restarting_runtime(
    tmp_path: Path, fetch_status: int
) -> None:
    deploy = (ROOT / "infra/gce/scripts/deploy-release.sh").read_text(encoding="utf-8")
    start = deploy.index("systemctl daemon-reload")
    end = deploy.index("\ncompose=(", start)
    assert "systemctl restart strayhub-secrets.service" not in deploy
    assert (
        end
        < deploy.index("production-preflight.sh")
        < deploy.index("systemctl stop strayhub.service")
    )
    candidate = tmp_path / "candidate"
    fetch = candidate / "infra/gce/scripts/fetch-secrets.sh"
    fetch.parent.mkdir(parents=True)
    fetch.write_text(
        f'#!/bin/bash\nprintf "fetch %s\\n" "$*" >> "$TRACE"\nexit {fetch_status}\n',
        encoding="utf-8",
    )
    fetch.chmod(0o755)
    secrets = tmp_path / "secrets"
    (secrets / "current").mkdir(parents=True)
    (secrets / "current/runtime.env").write_text("SYNTHETIC=1\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for command in ("systemctl", "chown"):
        stub = bin_dir / command
        stub.write_text(
            f'#!/bin/bash\nprintf "{command} %s\\n" "$*" >> "$TRACE"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
    trace = tmp_path / "trace"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'set -eu\nrelease_dir="$1"\nSECRETS_ROOT="$2"\n' + deploy[start:end],
            "--",
            str(candidate),
            str(secrets),
        ],
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "TRACE": str(trace)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == fetch_status
    calls = trace.read_text(encoding="utf-8").splitlines()
    assert calls[0] == "systemctl daemon-reload"
    assert f"--secret-map {candidate}/infra/gce/secrets/production-secret-map.tsv" in calls[1]
    assert "--environment prod" in calls[1]
    assert "--source-dir" not in calls[1]
    assert len(calls) == (3 if fetch_status == 0 else 2)


def test_ci_bootstrap_uses_root_owned_validated_candidate_before_execution() -> None:
    script = (ROOT / "infra/gce/scripts/deploy-release-ci.sh").read_text(encoding="utf-8")
    bootstrap = script.split("<<'BOOTSTRAP'\n", 1)[1].split("\nBOOTSTRAP", 1)[0]
    assert "/opt/strayhub/current/infra/gce/scripts/deploy-release.sh" not in script
    assert "mktemp -d /var/lib/strayhub/releases/.deploy-bootstrap.XXXXXX" in bootstrap
    steps = [
        "install -o root -g root -m 0444",
        '"$validator" validate-artifact',
        '[[ "$actual_sha" == "$expected_sha" ]]',
        '"$validator" extract-artifact',
        'chmod -R a-w "$bootstrap_dir"',
        'exec "$bootstrap_dir/payload/infra/gce/scripts/deploy-release.sh"',
    ]
    assert [bootstrap.index(step) for step in steps] == sorted(
        bootstrap.index(step) for step in steps
    )


@pytest.mark.parametrize("mismatch", [None, "beat", "redis"])
def test_production_preflight_rejects_inconsistent_broker_without_leaking_values(
    mismatch: str | None,
) -> None:
    script = (ROOT / "infra/gce/scripts/production-preflight.sh").read_text(encoding="utf-8")
    validator = script.split("config --format json | python3 -c '\n", 1)[1].split("\n'", 1)[0]
    services = {
        service: {
            "environment": {
                "CELERY_BROKER_URL": "redis://:synthetic-secret@redis:6379/0",
                "CELERY_AI_ENABLED": "false",
            }
        }
        for service in ("api", "worker", "celery-worker", "celery-beat")
    }
    services["redis"] = {"environment": {"REDIS_PASSWORD": "synthetic-secret"}}
    if mismatch == "beat":
        services["celery-beat"]["environment"]["CELERY_AI_ENABLED"] = "true"
    if mismatch == "redis":
        services["redis"]["environment"]["REDIS_PASSWORD"] = "different-secret"
    result = subprocess.run(
        [sys.executable, "-c", validator],
        input=json.dumps({"services": services}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if mismatch is None else 1)
    assert "synthetic-secret" not in result.stdout + result.stderr
    assert "different-secret" not in result.stdout + result.stderr
    assert "--entrypoint python celery-beat" in script


def build_artifact(tmp_path: Path, *, compatibility: str = "unknown") -> Path:
    payload = tmp_path / "payload"
    compose = payload / "infra/gce/docker-compose.production.yml"
    compose.parent.mkdir(parents=True)
    compose.write_text("services: {}\n", encoding="utf-8")
    (payload / "revision").write_text(f"{GIT_SHA}\n", encoding="utf-8")
    (payload / "image-digests.env").write_text(
        "".join(
            f"STRAYHUB_{service.upper()}_IMAGE={reference}\n"
            for service, reference in DIGESTS.items()
        ),
        encoding="utf-8",
    )
    script = payload / "infra/gce/scripts/verify.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    artifact = tmp_path / "artifact"
    artifact.mkdir()
    bundle = artifact / "deployment-bundle.tar"
    release_manifest.create_bundle(payload, bundle)
    args = argparse.Namespace(
        output=artifact / "release-manifest.json",
        release_id=RELEASE_ID,
        git_sha=GIT_SHA,
        created_at="2026-08-31T12:00:00Z",
        api_image=DIGESTS["api"],
        worker_image=DIGESTS["worker"],
        web_image=DIGESTS["web"],
        migration_revision="0037_animal_external_sources",
        schema_compatibility=compatibility,
        compose=compose,
        bundle=bundle,
        ci_run_id="12345",
        ci_workflow="GCE Release",
    )
    release_manifest.create_manifest(args)
    release_manifest.write_checksums(artifact)
    return artifact


@pytest.mark.parametrize(
    "reference",
    [
        "strayhub-api:latest",
        "strayhub-api:prod",
        "strayhub-api@sha256:1234",
        f"strayhub-api@sha512:{'1' * 64}",
        f"strayhub-api:main@sha256:{'1' * 64}",
    ],
)
def test_mutable_or_invalid_image_references_fail_closed(reference: str) -> None:
    with pytest.raises(release_manifest.ReleaseError):
        release_manifest.parse_image_reference(reference)


def test_successful_manifest_and_bundle_validation(tmp_path: Path) -> None:
    artifact = build_artifact(tmp_path)

    manifest = release_manifest.validate_artifact(artifact)
    extracted = tmp_path / "release"
    release_manifest.extract_artifact(artifact, extracted)

    assert manifest["git_sha"] == GIT_SHA
    assert manifest["schema_compatibility"] == "unknown"
    assert release_manifest.validate_release_dir(extracted)["release_id"] == RELEASE_ID
    assert (extracted / "infra/gce/scripts/verify.sh").stat().st_mode & 0o111


def test_bundle_allows_only_reviewed_nonsecret_acceptance_template(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    accepted = payload / "infra/gce/.env.acceptance.template"
    accepted.parent.mkdir(parents=True)
    accepted.write_text("APP_ENV=acceptance\n", encoding="utf-8")
    release_manifest.create_bundle(payload, tmp_path / "accepted.tar")

    rejected = payload / ".env.secret"
    rejected.write_text("SECRET=value\n", encoding="utf-8")
    with pytest.raises(release_manifest.ReleaseError, match="environment file forbidden"):
        release_manifest.create_bundle(payload, tmp_path / "rejected.tar")


def test_missing_manifest_field_is_rejected(tmp_path: Path) -> None:
    artifact = build_artifact(tmp_path)
    manifest_path = artifact / "release-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data.pop("migration_revision")
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(release_manifest.ReleaseError, match="missing fields"):
        release_manifest.load_manifest(manifest_path)


def test_invalid_git_sha_is_rejected(tmp_path: Path) -> None:
    artifact = build_artifact(tmp_path)
    manifest_path = artifact / "release-manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["git_sha"] = "short"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(release_manifest.ReleaseError, match="invalid git_sha"):
        release_manifest.load_manifest(manifest_path)


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    artifact = build_artifact(tmp_path)
    with (artifact / "deployment-bundle.tar").open("ab") as bundle:
        bundle.write(b"tampered")

    with pytest.raises(release_manifest.ReleaseError, match="checksum mismatch"):
        release_manifest.validate_artifact(artifact)


@pytest.mark.parametrize("compatibility", ["unknown", "forward-only"])
def test_rollback_refuses_unknown_or_incompatible_schema(
    tmp_path: Path, compatibility: str
) -> None:
    artifact = build_artifact(tmp_path, compatibility=compatibility)
    receipt = tmp_path / "current.json"
    receipt.write_text(
        json.dumps(
            {
                "release_id": RELEASE_ID,
                "previous_release_id": PREVIOUS_RELEASE,
                "verification": "passed",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(release_manifest.ReleaseError, match="rollback refused"):
        release_manifest.validate_rollback(
            artifact / "release-manifest.json", PREVIOUS_RELEASE, receipt
        )


def test_rollback_accepts_only_recorded_previous_release_when_explicitly_safe(
    tmp_path: Path,
) -> None:
    artifact = build_artifact(tmp_path, compatibility="backward-compatible-with-previous")
    receipt = tmp_path / "current.json"
    receipt.write_text(
        json.dumps(
            {
                "release_id": RELEASE_ID,
                "previous_release_id": PREVIOUS_RELEASE,
                "verification": "passed",
            }
        ),
        encoding="utf-8",
    )

    release_manifest.validate_rollback(
        artifact / "release-manifest.json", PREVIOUS_RELEASE, receipt
    )
    with pytest.raises(release_manifest.ReleaseError, match="not the recorded N-1"):
        release_manifest.validate_rollback(
            artifact / "release-manifest.json",
            f"20260829T120000Z-{'c' * 12}",
            receipt,
        )


def test_rollforward_accepts_only_recorded_newer_release_at_same_migration(
    tmp_path: Path,
) -> None:
    current_artifact = build_artifact(tmp_path / "current")
    target_artifact = build_artifact(tmp_path / "target")
    current_manifest = current_artifact / "release-manifest.json"
    target_manifest = target_artifact / "release-manifest.json"
    current = json.loads(current_manifest.read_text(encoding="utf-8"))
    current["release_id"] = PREVIOUS_RELEASE
    current["git_sha"] = "b" * 40
    current["created_at"] = "2026-08-30T12:00:00Z"
    current_manifest.write_text(json.dumps(current), encoding="utf-8")
    receipt = tmp_path / "current.json"
    receipt.write_text(
        json.dumps(
            {
                "release_id": PREVIOUS_RELEASE,
                "previous_release_id": RELEASE_ID,
                "verification": "passed",
            }
        ),
        encoding="utf-8",
    )

    release_manifest.validate_rollforward(current_manifest, target_manifest, receipt)

    original_argv = sys.argv
    sys.argv = [
        str(TOOL_PATH),
        "validate-rollforward",
        "--current-manifest",
        str(current_manifest),
        "--target-manifest",
        str(target_manifest),
        "--receipt",
        str(receipt),
    ]
    try:
        assert release_manifest.main() == 0
    finally:
        sys.argv = original_argv

    wrong_receipt = json.loads(receipt.read_text(encoding="utf-8"))
    wrong_receipt["previous_release_id"] = f"20260829T120000Z-{'c' * 12}"
    receipt.write_text(json.dumps(wrong_receipt), encoding="utf-8")
    with pytest.raises(release_manifest.ReleaseError, match="not the recorded previous release"):
        release_manifest.validate_rollforward(current_manifest, target_manifest, receipt)
    wrong_receipt["previous_release_id"] = RELEASE_ID
    receipt.write_text(json.dumps(wrong_receipt), encoding="utf-8")

    target = json.loads(target_manifest.read_text(encoding="utf-8"))
    target["created_at"] = current["created_at"]
    target_manifest.write_text(json.dumps(target), encoding="utf-8")
    with pytest.raises(release_manifest.ReleaseError, match="not newer"):
        release_manifest.validate_rollforward(current_manifest, target_manifest, receipt)
    target["created_at"] = "2026-08-31T12:00:00Z"
    target["migration_revision"] = "0038_incompatible"
    target_manifest.write_text(json.dumps(target), encoding="utf-8")
    with pytest.raises(release_manifest.ReleaseError, match="same migration revision"):
        release_manifest.validate_rollforward(current_manifest, target_manifest, receipt)


def test_repository_release_wiring_is_digest_aware_and_systemd_canonical() -> None:
    compose = (ROOT / "infra/gce/docker-compose.production.yml").read_text(encoding="utf-8")
    service = (ROOT / "infra/gce/systemd/strayhub.service").read_text(encoding="utf-8")
    migration = (ROOT / "infra/gce/systemd/strayhub-migrate.service").read_text(encoding="utf-8")
    deploy = (ROOT / "infra/gce/scripts/deploy-release.sh").read_text(encoding="utf-8")
    rollback = (ROOT / "infra/gce/scripts/rollback-release.sh").read_text(encoding="utf-8")
    rollforward = (ROOT / "infra/gce/scripts/rollforward-release.sh").read_text(encoding="utf-8")
    ci_deploy = (ROOT / "infra/gce/scripts/deploy-release-ci.sh").read_text(encoding="utf-8")
    receipt_verify = (ROOT / "infra/gce/scripts/verify-release-receipt.sh").read_text(
        encoding="utf-8"
    )

    for variable in ("STRAYHUB_API_IMAGE", "STRAYHUB_WORKER_IMAGE", "STRAYHUB_WEB_IMAGE"):
        assert variable in compose
    assert "image-digests.env" in service
    assert "--no-build" in service
    assert "image-digests.env" in migration
    assert "systemctl restart strayhub.service" in deploy
    assert "production-preflight.sh" in deploy
    assert "verify-systemd-runtime.sh" in deploy
    assert "alembic downgrade" not in deploy.lower()
    assert "validate-rollback" in rollback
    assert "validate-rollforward" in rollforward
    assert "alembic downgrade" not in rollback.lower()
    assert "down -v" not in deploy
    assert "down -v" not in rollback
    assert "down -v" not in rollforward
    assert deploy.index("validate-artifact") < deploy.index("systemctl stop strayhub.service")
    assert deploy.index("production-preflight.sh") < deploy.index("systemctl stop strayhub.service")
    assert deploy.index("--profile tools run --rm migration") < deploy.index(
        'mv -Tf "$temporary_link"'
    )
    assert rollback.index("validate-rollback") < rollback.index("systemctl stop strayhub.service")
    assert rollforward.index("validate-rollforward") < rollforward.index(
        "systemctl stop strayhub.service"
    )
    assert rollforward.index("temporary roll-forward pointer exists") < rollforward.index(
        "systemctl stop strayhub.service"
    )
    assert "--tunnel-through-iap" in ci_deploy
    assert "validate-artifact" in ci_deploy
    assert ci_deploy.index("validate-artifact") < ci_deploy.index("gcloud compute scp")
    assert 'exec "$bootstrap_dir/payload/infra/gce/scripts/deploy-release.sh"' in ci_deploy
    assert "DEPLOY_STRAYHUB_PRODUCTION" in ci_deploy
    assert "alembic downgrade" not in ci_deploy.lower()
    assert "/opt/strayhub/current" in receipt_verify
    assert "validate-release-dir" in receipt_verify
    assert "verify-systemd-runtime.sh" in receipt_verify
    assert 'receipt.get("verification") != "passed"' in receipt_verify


def test_gce_release_workflow_automatically_deploys_exact_release_branch_sha() -> None:
    workflow = (ROOT / ".github/workflows/gce-release.yml").read_text(encoding="utf-8")
    ci_workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release_push = workflow.split("  push:", maxsplit=1)[1].split(
        "  workflow_dispatch:", maxsplit=1
    )[0]
    publication = workflow.split("  publish-release:", maxsplit=1)[1].split(
        "  deploy-production:", maxsplit=1
    )[0]
    deployment = workflow.split("  deploy-production:", maxsplit=1)[1].split(
        "  verify-production:", maxsplit=1
    )[0]

    assert "id-token: write" in workflow
    assert "google-github-actions/auth" in workflow
    assert "workflow_dispatch" in workflow
    assert "branches: [main, release]" in workflow
    assert "paths:" not in release_push
    assert "workflow_call:" in ci_workflow
    assert "environment: release-publication" in workflow
    assert "name: production" in workflow
    assert "build-release-bundle.sh" in workflow
    assert "deploy-production:" in workflow
    assert "verify-production:" in workflow
    assert "uses: ./.github/workflows/ci.yml" in workflow
    assert "needs: [full-quality-gate, verify-release]" in workflow
    assert "needs: publish-release" in workflow
    assert "github.ref == 'refs/heads/release'" in workflow
    assert "Refuse stale release candidates" in workflow
    assert "steps.artifact.outputs.artifact-id" in workflow
    assert '"/repos/$GITHUB_REPOSITORY/actions/artifacts/$ARTIFACT_ID/zip"' in workflow
    assert "sha256sum --check" in workflow
    assert "deploy-release-ci.sh" in workflow
    assert "verify-release-receipt.sh" in workflow
    assert "--tunnel-through-iap" in workflow
    assert "GCP_RELEASE_DEPLOYER_SERVICE_ACCOUNT" in workflow
    assert "group: gce-immutable-release-${{ github.ref }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert publication.index("Require publication configuration") < publication.index(
        "google-github-actions/auth"
    )
    assert deployment.index("Download and validate release artifact") < deployment.index(
        "deploy-release-ci.sh"
    )
    assert deployment.index("Require deployment configuration") < deployment.index(
        "google-github-actions/auth"
    )
    assert "actions: read" in deployment
    assert "^[0-9a-f]{64}$" in deployment
    assert "terraform apply" not in workflow
    assert "service-account-key" not in workflow.lower()
    assert "alembic downgrade" not in workflow.lower()


def test_generated_release_bundle_is_excluded_from_git_and_images() -> None:
    assert "/release-bundle/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "release-bundle/" in (ROOT / ".dockerignore").read_text(encoding="utf-8")
