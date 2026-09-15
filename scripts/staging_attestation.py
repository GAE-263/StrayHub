"""Bind hosted Docker acceptance to GitHub run and immutable publication identities."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import zipfile
from pathlib import Path

from scripts.local_staging import ROOT, read_env_file, verify_e2e
from scripts.manual_release_gate import _load_json

REPOSITORY = "GAE-263/StrayHub"
WORKFLOW = ".github/workflows/build-release.yml"
REGISTRY = "asia-east1-docker.pkg.dev/canvas-primacy-502703-k1/strayhub"
HEX = re.compile(r"[0-9a-f]{64}")
SHA = re.compile(r"[0-9a-f]{40}")
POSITIVE = re.compile(r"[1-9][0-9]*")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_name(sha: str, attempt: int) -> str:
    return f"strayhub-staging-{sha}-attempt-{attempt}"


def prepare(directory: Path) -> None:
    """Generate disposable runner-only secrets; never print or upload them."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    template = (ROOT / "infra/local/staging.env.template").read_text()
    template = "\n".join(line for line in template.splitlines() if not line.startswith("#")) + "\n"
    for placeholder in set(re.findall(r"REPLACE_[A-Z0-9_]+", template)):
        value = (
            base64.b64encode(secrets.token_bytes(32)).decode()
            if placeholder == "REPLACE_BASE64_32_BYTE_KEY"
            else secrets.token_hex(32)
        )
        template = template.replace(placeholder, value)
    private = directory / "staging-jwt-private.pem"
    public = directory / "staging-jwt-public.pem"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private),
        ],
        check=True,
        capture_output=True,
    )
    private.chmod(0o600)
    subprocess.run(
        ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
        check=True,
        capture_output=True,
    )
    template = template.replace("/REPLACE/staging-jwt-private.pem", str(private.resolve()))
    template = template.replace("/REPLACE/staging-jwt-public.pem", str(public.resolve()))
    require("REPLACE" not in template, "unresolved synthetic configuration")
    with (directory / "staging.env").open("x") as output:
        os.chmod(output.name, 0o600)
        output.write(template)


def validate_receipt(receipt: dict, sha: str, artifact: str) -> None:
    require(bool(SHA.fullmatch(sha)), "invalid source SHA")
    require(
        bool(
            re.fullmatch(re.escape(REGISTRY) + r"/strayhub-release@sha256:[0-9a-f]{64}", artifact)
        ),
        "invalid OCI release reference",
    )
    require(
        receipt.get("git_sha") == sha and receipt.get("artifact_image") == artifact,
        "staging release identity mismatch",
    )
    require(receipt.get("scope") == "local-docker-staging", "unexpected acceptance scope")
    require(receipt.get("production_promotion_approved") is False, "invalid local approval")
    require(receipt.get("runtime") == "PASS", "runtime did not pass")
    require(receipt.get("cloud_checks") == "NOT_APPLICABLE_LOCAL", "invalid cloud scope")
    require(receipt.get("loopback_ingress", {}).get("status") == "PASS", "ingress did not pass")
    migration = receipt.get("migration_revision", {})
    require(
        bool(migration.get("expected")) and migration.get("expected") == migration.get("actual"),
        "migration mismatch",
    )
    e2e = receipt.get("authenticated_e2e", {})
    require(e2e.get("status") == "PASS", "E2E did not pass")
    verify_e2e(e2e, "staging_app")
    for field in ("manifest_sha256", "bundle_sha256"):
        require(bool(HEX.fullmatch(receipt.get(field, ""))), f"invalid {field}")
    images = receipt.get("images", {})
    require(set(images) == {"api", "worker", "web"}, "unexpected image set")
    for service, image in images.items():
        require(
            bool(
                re.fullmatch(
                    re.escape(f"{REGISTRY}/strayhub-{service}") + r"@sha256:[0-9a-f]{64}", image
                )
            ),
            "invalid image reference",
        )
    expected_contract = {
        "runner": checksum(ROOT / "scripts/local_staging.py"),
        "overlay": checksum(ROOT / "infra/gce/docker-compose.staging.yml"),
    }
    require(receipt.get("contract_sha256") == expected_contract, "acceptance contract mismatch")


def create(receipt_path: Path, output: Path, sha: str, artifact: str) -> None:
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "wrong repository")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "wrong ref")
    require(os.environ.get("GITHUB_SHA") == sha, "workflow/source SHA mismatch")
    require(
        os.environ.get("GITHUB_WORKFLOW_REF") == f"{REPOSITORY}/{WORKFLOW}@refs/heads/main",
        "wrong workflow",
    )
    require(os.environ.get("STAGING_RUNNER_ENVIRONMENT") == "github-hosted", "not a hosted runner")
    require(os.environ.get("GITHUB_EVENT_NAME") in {"push", "workflow_dispatch"}, "wrong event")
    run_id, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    require(bool(POSITIVE.fullmatch(run_id)) and bool(POSITIVE.fullmatch(attempt)), "invalid run")
    receipt = _load_json(receipt_path)
    validate_receipt(receipt, sha, artifact)
    document = {
        "schema_version": 1,
        "scope": "github-hosted-docker-staging",
        "status": "PASS",
        "repository": REPOSITORY,
        "workflow": WORKFLOW,
        "run_id": int(run_id),
        "run_attempt": int(attempt),
        "workflow_sha": sha,
        "receipt": receipt,
    }
    with output.open("x") as stream:
        json.dump(document, stream, sort_keys=True, indent=2)
        stream.write("\n")


def validate_evidence(
    document: dict,
    run: dict,
    metadata: dict,
    *,
    run_id: int,
    artifact_id: int,
    digest: str,
    sha: str,
    bundle: str,
    manifest: dict,
    manifest_digest: str,
    artifact: str,
) -> None:
    require(
        run.get("id") == run_id
        and run.get("repository", {}).get("full_name") == REPOSITORY
        and run.get("head_repository", {}).get("full_name") == REPOSITORY,
        "staging run repository mismatch",
    )
    require(
        run.get("path") == WORKFLOW
        and run.get("head_branch") == "main"
        and run.get("head_sha") == sha
        and run.get("event") in {"push", "workflow_dispatch"}
        and run.get("status") == "completed"
        and run.get("conclusion") == "success",
        "staging run is not a successful trusted main run",
    )
    attempt = run.get("run_attempt")
    require(type(attempt) is int and attempt > 0, "invalid staging attempt")
    require(
        metadata.get("id") == artifact_id
        and metadata.get("expired") is False
        and metadata.get("name") == artifact_name(sha, attempt)
        and metadata.get("digest") == f"sha256:{digest}"
        and metadata.get("workflow_run", {}).get("id") == run_id
        and metadata.get("workflow_run", {}).get("head_sha") == sha,
        "staging artifact metadata mismatch",
    )
    expected = {
        "schema_version": 1,
        "scope": "github-hosted-docker-staging",
        "status": "PASS",
        "repository": REPOSITORY,
        "workflow": WORKFLOW,
        "run_id": run_id,
        "run_attempt": attempt,
        "workflow_sha": sha,
    }
    require(
        set(document) == set(expected) | {"receipt"}
        and all(document.get(key) == value for key, value in expected.items()),
        "staging attestation provenance mismatch",
    )
    receipt = document["receipt"]
    validate_receipt(receipt, sha, artifact)
    images = {
        name: value["repository"] + "@" + value["digest"]
        for name, value in manifest["images"].items()
    }
    require(
        receipt["images"] == images
        and receipt["bundle_sha256"] == bundle
        and manifest["release_bundle_sha256"] == bundle
        and receipt["manifest_sha256"] == manifest_digest
        and manifest["git_sha"] == sha
        and receipt["release_id"] == manifest["release_id"]
        and receipt["migration_revision"]["actual"] == manifest["migration_revision"],
        "staging and production artifact identities differ",
    )


def read_archive(raw: bytes, digest: str) -> dict:
    require(
        len(raw) < 1_000_000 and hashlib.sha256(raw).hexdigest() == digest,
        "attestation archive checksum/size mismatch",
    )
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        require(
            len(entries) == 1
            and entries[0].filename == "staging-attestation.json"
            and entries[0].file_size < 100_000,
            "unexpected attestation archive contents",
        )

        # No filesystem extraction, and duplicate JSON keys are rejected.
        def unique(pairs: list) -> dict:
            result = {}
            for key, value in pairs:
                require(key not in result, "duplicate attestation JSON key")
                result[key] = value
            return result

        return json.loads(archive.read(entries[0]), object_pairs_hook=unique)


def gh(endpoint: str) -> bytes:
    result = subprocess.run(
        ["gh", "api", "--method", "GET", endpoint], capture_output=True, check=True, timeout=60
    )
    return result.stdout


def verify(args: argparse.Namespace) -> None:
    require(bool(POSITIVE.fullmatch(args.run_id)), "invalid staging run ID")
    match = re.fullmatch(r"([1-9][0-9]*):([0-9a-f]{64})", args.artifact_identity)
    require(match is not None, "expected staging artifact ID:SHA256")
    assert match
    artifact_id, digest = int(match[1]), match[2]
    prefix = f"repos/{REPOSITORY}/actions"
    run = json.loads(gh(f"{prefix}/runs/{args.run_id}"))
    metadata = json.loads(gh(f"{prefix}/artifacts/{artifact_id}"))
    # Reject unrelated/expired/oversized archives before downloading them.
    require(
        metadata.get("workflow_run", {}).get("id") == int(args.run_id)
        and metadata.get("expired") is False
        and 0 < metadata.get("size_in_bytes", 0) < 1_000_000,
        "invalid staging archive",
    )
    document = read_archive(gh(f"{prefix}/artifacts/{artifact_id}/zip"), digest)
    directory = args.publication
    identity = read_env_file(directory / "artifact-identity.env")
    validate_evidence(
        document,
        run,
        metadata,
        run_id=int(args.run_id),
        artifact_id=artifact_id,
        digest=digest,
        sha=args.git_sha,
        bundle=args.bundle_sha256,
        manifest=_load_json(directory / "release-manifest.json"),
        manifest_digest=checksum(directory / "release-manifest.json"),
        artifact=identity["artifact_image"],
    )
    print("Hosted staging evidence matches the exact production publication: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--directory", type=Path, required=True)
    attest = commands.add_parser("create")
    attest.add_argument("--receipt", type=Path, required=True)
    attest.add_argument("--output", type=Path, required=True)
    attest.add_argument("--git-sha", required=True)
    attest.add_argument("--artifact", required=True)
    check = commands.add_parser("verify")
    check.add_argument("--run-id", required=True)
    check.add_argument("--artifact-identity", required=True)
    check.add_argument("--git-sha", required=True)
    check.add_argument("--bundle-sha256", required=True)
    check.add_argument("--publication", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.directory)
    elif args.command == "create":
        create(args.receipt, args.output, args.git_sha, args.artifact)
    else:
        verify(args)


if __name__ == "__main__":
    main()
