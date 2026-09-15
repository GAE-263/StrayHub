from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import subprocess
import zipfile

import pytest
import yaml
from scripts import staging_attestation as gate


@pytest.fixture
def evidence():
    sha, bundle, digest = "a" * 40, "b" * 64, "c" * 64
    artifact = f"{gate.REGISTRY}/strayhub-release@sha256:" + "d" * 64
    images = {
        name: {"repository": f"{gate.REGISTRY}/strayhub-{name}", "digest": "sha256:" + char * 64}
        for name, char in (("api", "1"), ("worker", "2"), ("web", "3"))
    }
    manifest = {
        "git_sha": sha,
        "release_id": "20260915T130904Z-aaaaaaaaaaaa",
        "release_bundle_sha256": bundle,
        "migration_revision": "0056_test",
        "images": images,
    }
    receipt = {
        "git_sha": sha,
        "release_id": manifest["release_id"],
        "artifact_image": artifact,
        "scope": "local-docker-staging",
        "production_promotion_approved": False,
        "runtime": "PASS",
        "cloud_checks": "NOT_APPLICABLE_LOCAL",
        "loopback_ingress": {"status": "PASS"},
        "migration_revision": {"expected": "0056_test", "actual": "0056_test"},
        "manifest_sha256": digest,
        "bundle_sha256": bundle,
        "images": {
            name: image["repository"] + "@" + image["digest"] for name, image in images.items()
        },
        "contract_sha256": {
            "runner": gate.checksum(gate.ROOT / "scripts/local_staging.py"),
            "overlay": gate.checksum(gate.ROOT / "infra/gce/docker-compose.staging.yml"),
        },
        "authenticated_e2e": {
            **dict.fromkeys(
                (
                    "status",
                    "valid_login",
                    "invalid_auth",
                    "authenticated_api",
                    "tenant_a_positive",
                    "tenant_b_negative",
                    "volunteer_grant",
                    "qr_first",
                    "care_report",
                    "cross_shelter_denial",
                ),
                "PASS",
            ),
            "runtime_role": "staging_app",
            "runtime_bypassrls": False,
            "runtime_superuser": False,
            "rls_table_count": 48,
        },
    }
    document = {
        "schema_version": 1,
        "scope": "github-hosted-docker-staging",
        "status": "PASS",
        "repository": gate.REPOSITORY,
        "workflow": gate.WORKFLOW,
        "run_id": 123,
        "run_attempt": 2,
        "workflow_sha": sha,
        "receipt": receipt,
    }
    run = {
        "id": 123,
        "repository": {"full_name": gate.REPOSITORY},
        "head_repository": {"full_name": gate.REPOSITORY},
        "path": gate.WORKFLOW,
        "head_branch": "main",
        "head_sha": sha,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 2,
    }
    metadata = {
        "id": 456,
        "name": gate.artifact_name(sha, 2),
        "expired": False,
        "digest": "sha256:" + digest,
        "workflow_run": {"id": 123, "head_sha": sha},
    }
    args = dict(
        run_id=123,
        artifact_id=456,
        digest=digest,
        sha=sha,
        bundle=bundle,
        manifest=manifest,
        manifest_digest=digest,
        artifact=artifact,
    )
    return document, run, metadata, args


def test_exact_hosted_evidence_passes(evidence):
    document, run, metadata, args = evidence
    gate.validate_evidence(document, run, metadata, **args)


@pytest.mark.parametrize(
    "target,key,value",
    [
        ("run", "id", 999),
        ("run", "head_sha", "f" * 40),
        ("run", "head_branch", "release"),
        ("run", "event", "pull_request"),
        ("run", "path", ".github/workflows/ci.yml"),
        ("run", "conclusion", "failure"),
        ("run", "status", "in_progress"),
        ("run", "run_attempt", 3),
        ("run", "head_repository", {"full_name": "attacker/StrayHub"}),
        ("metadata", "id", 789),
        ("metadata", "expired", True),
        ("metadata", "digest", "sha256:" + "f" * 64),
        ("metadata", "workflow_run", {"id": 999, "head_sha": "a" * 40}),
        ("metadata", "name", "strayhub-staging-other"),
        ("document", "scope", "local-docker-staging"),
        ("document", "run_id", 999),
        ("document", "run_attempt", 1),
        ("document", "workflow_sha", "f" * 40),
        ("document", "status", "FAIL"),
        ("receipt", "bundle_sha256", "f" * 64),
        ("receipt", "manifest_sha256", "f" * 64),
        ("receipt", "runtime", "FAIL"),
        ("receipt", "production_promotion_approved", True),
        ("receipt", "contract_sha256", {}),
        ("receipt", "loopback_ingress", {"status": "FAIL"}),
        ("receipt", "migration_revision", {"expected": "0056_test", "actual": "old"}),
    ],
)
def test_mixed_failed_or_stale_evidence_rejected(evidence, target, key, value):
    document, run, metadata, args = copy.deepcopy(evidence)
    targets = {
        "document": document,
        "run": run,
        "metadata": metadata,
        "receipt": document["receipt"],
    }
    targets[target][key] = value
    with pytest.raises(ValueError):
        gate.validate_evidence(document, run, metadata, **args)


@pytest.mark.parametrize("service", ["api", "worker", "web"])
def test_each_image_digest_is_bound(evidence, service):
    document, run, metadata, args = copy.deepcopy(evidence)
    args["manifest"]["images"][service]["digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="identities differ"):
        gate.validate_evidence(document, run, metadata, **args)


@pytest.mark.parametrize(
    "key,value",
    [
        ("cross_shelter_denial", "FAIL"),
        ("runtime_bypassrls", True),
        ("runtime_superuser", True),
        ("runtime_role", "postgres"),
        ("rls_table_count", 0),
    ],
)
def test_tenant_isolation_required(evidence, key, value):
    document, run, metadata, args = copy.deepcopy(evidence)
    document["receipt"]["authenticated_e2e"][key] = value
    with pytest.raises(ValueError):
        gate.validate_evidence(document, run, metadata, **args)


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name, content in files:
            target.writestr(name, content)
    return output.getvalue()


def test_archive_checksum_and_structure():
    raw = archive([("staging-attestation.json", '{"status":"PASS"}')])
    assert gate.read_archive(raw, hashlib.sha256(raw).hexdigest()) == {"status": "PASS"}
    with pytest.raises(ValueError):
        gate.read_archive(raw, "f" * 64)
    for files in (
        [("../staging-attestation.json", "{}")],
        [("staging-attestation.json", "{}"), ("extra", "{}")],
        [("staging-attestation.json", '{"status":"PASS","status":"FAIL"}')],
    ):
        raw = archive(files)
        with pytest.raises(ValueError):
            gate.read_archive(raw, hashlib.sha256(raw).hexdigest())


def test_prepare_generates_private_distinct_synthetic_secrets(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    gate.prepare(first)
    gate.prepare(second)
    one, two = gate.read_env_file(first / "staging.env"), gate.read_env_file(second / "staging.env")
    assert one["POSTGRES_PASSWORD"] != two["POSTGRES_PASSWORD"]
    assert one["POSTGRES_PASSWORD"] in one["DATABASE_MIGRATION_URL"]
    assert one["POSTGRES_RUNTIME_PASSWORD"] in one["DATABASE_URL"]
    assert (first / "staging.env").stat().st_mode & 0o077 == 0
    assert (first / "staging-jwt-private.pem").stat().st_mode & 0o077 == 0
    assert "REPLACE" not in (first / "staging.env").read_text()
    with pytest.raises(FileExistsError):
        gate.prepare(first)


def test_generated_configuration_renders_isolated_canonical_runtime(tmp_path):
    directory = tmp_path / "secrets"
    gate.prepare(directory)
    environment = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    for service in ("api", "worker", "web"):
        environment[f"STRAYHUB_{service.upper()}_IMAGE"] = (
            f"{gate.REGISTRY}/strayhub-{service}@sha256:" + "a" * 64
        )
    base = [
        "docker",
        "compose",
        "--env-file",
        str(directory / "staging.env"),
        "-f",
        str(gate.ROOT / "infra/gce/docker-compose.production.yml"),
    ]

    def render(command):
        result = subprocess.run(
            command + ["--profile", "*", "config", "--format", "json"],
            env=environment,
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    reference = render(base)
    candidate = render(base + ["-f", str(gate.ROOT / "infra/gce/docker-compose.staging.yml")])
    from scripts.check_runtime_parity import compare
    from scripts.local_staging import validate_model

    validate_model(candidate)
    assert compare(reference, candidate, "staging") == []


def test_local_receipt_cannot_issue_hosted_attestation(evidence, tmp_path, monkeypatch):
    document, _, _, args = evidence
    source = tmp_path / "receipt.json"
    source.write_text(json.dumps(document["receipt"]))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(ValueError, match="repository"):
        gate.create(source, tmp_path / "staging-attestation.json", args["sha"], args["artifact"])


def test_hosted_creation_and_download_verification_roundtrip(evidence, tmp_path, monkeypatch):
    document, run, metadata, args = evidence
    for key, value in {
        "GITHUB_REPOSITORY": gate.REPOSITORY,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": args["sha"],
        "GITHUB_WORKFLOW_REF": f"{gate.REPOSITORY}/{gate.WORKFLOW}@refs/heads/main",
        "STAGING_RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
    }.items():
        monkeypatch.setenv(key, value)
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps(args["manifest"]))
    document["receipt"]["manifest_sha256"] = gate.checksum(manifest_path)
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(document["receipt"]))
    attestation = tmp_path / "staging-attestation.json"
    gate.create(receipt, attestation, args["sha"], args["artifact"])
    with pytest.raises(FileExistsError):
        gate.create(receipt, attestation, args["sha"], args["artifact"])
    (tmp_path / "artifact-identity.env").write_text(f"artifact_image={args['artifact']}\n")
    raw = archive([("staging-attestation.json", attestation.read_text())])
    digest = hashlib.sha256(raw).hexdigest()
    metadata.update(digest=f"sha256:{digest}", size_in_bytes=len(raw))
    prefix = f"repos/{gate.REPOSITORY}/actions"
    responses = {
        f"{prefix}/runs/123": json.dumps(run).encode(),
        f"{prefix}/artifacts/456": json.dumps(metadata).encode(),
        f"{prefix}/artifacts/456/zip": raw,
    }
    calls = []

    def fetch(endpoint):
        calls.append(endpoint)
        return responses[endpoint]

    monkeypatch.setattr(gate, "gh", fetch)
    namespace = argparse.Namespace(
        run_id="123",
        artifact_identity=f"456:{digest}",
        git_sha=args["sha"],
        bundle_sha256=args["bundle"],
        publication=tmp_path,
    )
    gate.verify(namespace)
    assert calls == list(responses)
    metadata["expired"] = True
    responses[f"{prefix}/artifacts/456"] = json.dumps(metadata).encode()
    calls.clear()
    with pytest.raises(ValueError, match="invalid staging archive"):
        gate.verify(namespace)
    assert f"{prefix}/artifacts/456/zip" not in calls


def test_workflow_gates_before_credentials_and_uploads_only_evidence():
    build = yaml.load((gate.ROOT / gate.WORKFLOW).read_text(), Loader=yaml.BaseLoader)
    job = build["jobs"]["staging"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["needs"] == "build-release"
    assert job["environment"] == "release-publication"
    steps = job["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "scripts.local_staging" in commands
    assert "scripts.staging_attestation create" in commands
    assert "build-immutable-release.sh" not in commands
    upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload"))
    assert upload["with"]["path"] == "${{ runner.temp }}/staging-attestation.json"
    assert "if" not in upload  # default success only, never always()
    release = yaml.load(
        (gate.ROOT / ".github/workflows/gce-release.yml").read_text(), Loader=yaml.BaseLoader
    )
    steps = release["jobs"]["deploy-production"]["steps"]
    gate_index = next(
        i
        for i, step in enumerate(steps)
        if "scripts.staging_attestation verify" in step.get("run", "")
    )
    auth_index = next(
        i
        for i, step in enumerate(steps)
        if step.get("uses", "").startswith("google-github-actions/auth")
    )
    assert gate_index < auth_index
    assert "if" not in steps[gate_index] and "continue-on-error" not in steps[gate_index]
