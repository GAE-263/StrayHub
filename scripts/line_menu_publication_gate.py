"""Protected resource-publication gate for immutable LINE Rich Menu manifests.

This module never promotes a menu, links a user, deletes a resource, changes
runtime configuration, or imports application settings. Credentials are
accepted only by the CLI process that runs inside the protected workflow job.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx
from scripts.line_menu_manifest import (
    MenuManifestError,
    VerifiedMenuManifest,
    canonical_json,
    finalize_publication_manifest,
)
from scripts.line_menu_publication import PublicationError, ResourcePublisher, save_manifest
from scripts.sync_line_role_menus import (
    discover_definitions,
    publication_plan,
)

REQUIRED_ROLES = ("default", "volunteer", "adoption_hub")
BUCKET_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]")
RUN_ID = re.compile(r"[0-9]+")


class ImmutableStorageError(RuntimeError):
    """The authoritative object could not be safely created or verified."""


@dataclass(frozen=True)
class StoredObject:
    uri: str
    generation: str
    created: bool


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]]


def _run(args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, check=False, capture_output=True, timeout=60)


class GcloudImmutableStore:
    """Content-addressed GCS writes with an object-generation create precondition."""

    def __init__(self, bucket: str, *, runner: Runner = _run):
        if not BUCKET_NAME.fullmatch(bucket):
            raise ImmutableStorageError("protected manifest bucket name is invalid")
        self.bucket = bucket
        self.runner = runner

    def put(self, namespace: str, content: bytes) -> StoredObject:
        if namespace not in {"line-rich-menu-manifests", "line-rich-menu-receipts"}:
            raise ImmutableStorageError("immutable object namespace is not allowed")
        content_hash = sha256(content).hexdigest()
        uri = f"gs://{self.bucket}/{namespace}/{content_hash}.json"
        with tempfile.NamedTemporaryFile(prefix="line-menu-object-", suffix=".json") as stream:
            stream.write(content)
            stream.flush()
            create = self.runner(
                [
                    "gcloud",
                    "storage",
                    "cp",
                    stream.name,
                    uri,
                    "--if-generation-match=0",
                    "--quiet",
                ]
            )
        existing = self.runner(["gcloud", "storage", "cat", uri])
        if existing.returncode != 0 or existing.stdout != content:
            raise ImmutableStorageError("immutable object readback mismatch or unavailable")
        created = create.returncode == 0
        if not created and existing.stdout != content:
            raise ImmutableStorageError("immutable object already exists with different content")
        describe = self.runner(["gcloud", "storage", "objects", "describe", uri, "--format=json"])
        try:
            metadata = json.loads(describe.stdout)
            generation = str(metadata["generation"])
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ImmutableStorageError("immutable object generation is unavailable") from exc
        if describe.returncode != 0 or not generation.isdigit():
            raise ImmutableStorageError("immutable object generation is invalid")
        return StoredObject(uri=uri, generation=generation, created=created)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".line-menu-receipt-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _orphan_candidates(progress_path: Path) -> list[str]:
    try:
        document = json.loads(progress_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    candidates = []
    for record in document.get("resources", {}).values():
        if not isinstance(record, dict) or record.get("stage") == "ready":
            continue
        resource_id = record.get("id")
        if isinstance(resource_id, str) and re.fullmatch(r"richmenu-[A-Za-z0-9-]+", resource_id):
            candidates.append(resource_id)
    return sorted(set(candidates))


def _base_receipt(*, git_sha: str, run_id: str, run_attempt: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation": "menu-publication",
        "workflow": {"run_id": run_id, "run_attempt": run_attempt},
        "repository": "GAE-263/StrayHub",
        "workflow_identity": ".github/workflows/line-rich-menu-publish.yml",
        "git_sha": git_sha,
        "timestamp": datetime.now(UTC).isoformat(),
        "global_default_changed": False,
        "per_user_binding_changed": False,
        "resources_deleted": False,
    }


def success_receipt(
    *,
    verified: VerifiedMenuManifest,
    outcomes: dict[str, str],
    stored: StoredObject,
    run_id: str,
    run_attempt: str,
) -> dict[str, object]:
    receipt = _base_receipt(git_sha=verified.git_sha, run_id=run_id, run_attempt=run_attempt)
    receipt.update(
        {
            "status": "success",
            "bot": {
                "basic_id": verified.bot_basic_id,
                "fingerprint": verified.bot_fingerprint,
            },
            "menus": {
                role: {**verified.menus[role], "publication": outcomes[role]}
                for role in REQUIRED_ROLES
            },
            "manifest": {
                "sha256": verified.manifest_sha256,
                "uri": stored.uri,
                "generation": stored.generation,
                "created": stored.created,
                "validator": "passed",
            },
        }
    )
    return receipt


def failure_receipt(
    *,
    git_sha: str,
    failure_gate: str,
    progress_path: Path,
    run_id: str,
    run_attempt: str,
    verified_manifest_created: bool = False,
    manifest_uploaded: bool = False,
    error_code: str = "resource_publication",
    candidate_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    receipt = _base_receipt(git_sha=git_sha, run_id=run_id, run_attempt=run_attempt)
    receipt.update(
        {
            "status": "failure",
            "failure_gate": failure_gate,
            "orphan_candidate_ids": _orphan_candidates(progress_path),
            "verified_manifest_created": verified_manifest_created,
            "manifest_uploaded": manifest_uploaded,
            "progress_sha256": (
                sha256(progress_path.read_bytes()).hexdigest() if progress_path.exists() else None
            ),
            "error_code": error_code,
            "candidate_ids": sorted(set(candidate_ids)),
        }
    )
    return receipt


async def run_gate(
    *,
    publisher: ResourcePublisher,
    plan: dict[str, dict],
    progress_path: Path,
    final_path: Path,
    receipt_path: Path,
    expected_bot: str,
    git_sha: str,
    store: GcloudImmutableStore,
    run_id: str,
    run_attempt: str,
    recovery_identity: dict | None = None,
) -> dict[str, object]:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    verified_manifest_created = False
    manifest_uploaded = False
    gate = "resource_publication"
    try:
        if recovery_identity is None:
            await publisher.publish(plan, progress_path, expected_bot, git_sha)
        else:
            await publisher.publish(
                plan,
                progress_path,
                expected_bot,
                git_sha,
                recovery_identity=recovery_identity,
            )
        gate = "manifest_validation"
        verified = finalize_publication_manifest(
            progress_path,
            final_path,
            expected_git_sha=git_sha,
            expected_bot_basic_id=expected_bot,
        )
        verified_manifest_created = True
        if recovery_identity is not None:
            progress = json.loads(progress_path.read_bytes())
            progress["recovery"]["manifest_produced"] = True
            save_manifest(progress_path, progress)
        gate = "immutable_manifest_storage"
        stored_manifest = store.put("line-rich-menu-manifests", final_path.read_bytes())
        manifest_uploaded = True
        if recovery_identity is not None:
            progress = json.loads(progress_path.read_bytes())
            progress["recovery"]["manifest_uploaded"] = True
            save_manifest(progress_path, progress)
        receipt = success_receipt(
            verified=verified,
            outcomes=publisher.outcomes,
            stored=stored_manifest,
            run_id=run_id,
            run_attempt=run_attempt,
        )
        receipt_bytes = canonical_json(receipt)
        _atomic_write(receipt_path, receipt_bytes)
        gate = "immutable_receipt_storage"
        store.put("line-rich-menu-receipts", receipt_bytes)
        return receipt
    except (
        PublicationError,
        MenuManifestError,
        ImmutableStorageError,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        receipt = failure_receipt(
            git_sha=git_sha,
            failure_gate=gate,
            progress_path=progress_path,
            run_id=run_id,
            run_attempt=run_attempt,
            verified_manifest_created=verified_manifest_created,
            manifest_uploaded=manifest_uploaded,
            error_code=getattr(exc, "code", gate),
            candidate_ids=getattr(exc, "candidate_ids", ()),
        )
        _atomic_write(receipt_path, canonical_json(receipt))
        raise PublicationError(
            f"Publication stopped at {gate}; see sanitized failure receipt"
        ) from None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--expected-bot", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--image-dir", type=Path, default=Path("infra/local/rich-menu-images"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.git_sha):
        parser.error("--git-sha must be a full lowercase SHA")
    if not RUN_ID.fullmatch(args.run_id) or not RUN_ID.fullmatch(args.run_attempt):
        parser.error("workflow run identity must be numeric")
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        parser.error("LINE_CHANNEL_ACCESS_TOKEN is required in the protected publish job")
    definitions = discover_definitions()
    plan = publication_plan({role: definitions[role] for role in REQUIRED_ROLES}, args.image_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    async def execute() -> dict[str, object]:
        progress_path = args.output_dir / "progress.json"
        if progress_path.exists():
            try:
                recovery_identity = json.loads(progress_path.read_bytes())["recovery"]
            except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PublicationError("Recovered progress identity is invalid; STOP") from exc
            if (
                not isinstance(recovery_identity, dict)
                or recovery_identity.get("run_id") != args.run_id
                or recovery_identity.get("run_attempt") != args.run_attempt
            ):
                raise PublicationError("Recovered progress run identity mismatch; STOP")
        else:
            recovery_identity = {
                "schema_version": 1,
                "repository": "GAE-263/StrayHub",
                "workflow": ".github/workflows/line-rich-menu-publish.yml",
                "run_id": args.run_id,
                "run_attempt": args.run_attempt,
                "operation": "publish",
                "created_at": datetime.now(UTC).isoformat(),
                "manifest_produced": False,
                "manifest_uploaded": False,
            }
        async with httpx.AsyncClient(
            timeout=20,
            trust_env=False,
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            return await run_gate(
                publisher=ResourcePublisher(client),
                plan=plan,
                progress_path=progress_path,
                final_path=args.output_dir / "verified-manifest.json",
                receipt_path=args.output_dir / "receipt.json",
                expected_bot=args.expected_bot,
                git_sha=args.git_sha,
                store=GcloudImmutableStore(args.bucket),
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                recovery_identity=recovery_identity,
            )

    try:
        receipt = asyncio.run(execute())
    except PublicationError as exc:
        parser.exit(
            1,
            f"{exc}\nNo promotion, binding, deletion, config sync or deployment performed.\n",
        )
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "manifest": receipt["manifest"],
                "receipt_path": str(args.output_dir / "receipt.json"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
