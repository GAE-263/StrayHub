"""Fail-closed recovery of sanitized LINE publication progress from GitHub Actions.

The recovered artifact is only resumable state. It is never an authoritative
runtime manifest and this module performs no LINE or GCP operation.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
from scripts.line_menu_publication import canonical
from scripts.sync_line_role_menus import discover_definitions, publication_plan

REPOSITORY = "GAE-263/StrayHub"
WORKFLOW = ".github/workflows/line-rich-menu-publish.yml"
PUBLISH_JOB = "Create or reuse resources and store verified manifest"
ROLES = frozenset(("default", "volunteer", "adoption_hub"))
RUN_ID = re.compile(r"[1-9][0-9]*")
SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
MENU_ID = re.compile(r"richmenu-[A-Za-z0-9-]+")
BOT_ID = re.compile(r"@[A-Za-z0-9._-]+")
MAX_ARCHIVE_BYTES = 1_048_576
MAX_AGE = timedelta(days=30)


class RecoveryError(RuntimeError):
    """Sanitized recovery failure suitable for workflow output."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryError("resume_source_invalid: duplicate JSON key")
        result[key] = value
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"resume_source_invalid: invalid {label}") from exc
    if not isinstance(value, dict):
        raise RecoveryError(f"resume_source_invalid: {label} must be an object")
    return value


def _keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise RecoveryError(f"resume_source_invalid: invalid {label} fields")


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise RecoveryError("resume_source_invalid: timestamp missing")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RecoveryError("resume_source_invalid: timestamp invalid") from exc
    if parsed.tzinfo is None:
        raise RecoveryError("resume_source_invalid: timestamp timezone missing")
    return parsed.astimezone(UTC)


def _extract(archive: bytes) -> tuple[bytes, bytes]:
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise RecoveryError("resume_source_invalid: artifact is oversized")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            infos = bundle.infolist()
            if {item.filename for item in infos} != {"progress.json", "receipt.json"}:
                raise RecoveryError("resume_source_invalid: unexpected artifact members")
            if len(infos) != 2:
                raise RecoveryError("resume_source_invalid: duplicate artifact members")
            if sum(item.file_size for item in infos) > MAX_ARCHIVE_BYTES:
                raise RecoveryError("resume_source_invalid: artifact content is oversized")
            for item in infos:
                mode = item.external_attr >> 16
                if (
                    item.filename.startswith("/")
                    or ".." in Path(item.filename).parts
                    or "/" in item.filename
                    or stat.S_ISLNK(mode)
                    or item.file_size > MAX_ARCHIVE_BYTES
                ):
                    raise RecoveryError("resume_source_invalid: unsafe artifact member")
            return bundle.read("progress.json"), bundle.read("receipt.json")
    except RecoveryError:
        raise
    except (zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise RecoveryError("resume_source_invalid: invalid artifact archive") from exc


def _validate_progress(
    raw: bytes,
    *,
    plan: dict[str, dict],
    git_sha: str,
    expected_bot: str,
    source_run_id: str,
    source_attempt: str,
    manifest_produced: bool,
    now: datetime,
) -> dict[str, Any]:
    progress = _json(raw, "progress")
    _keys(progress, {"schema", "git_sha", "bot", "resources", "updated_at", "recovery"}, "progress")
    if progress["schema"] != 1 or progress["git_sha"] != git_sha:
        raise RecoveryError("resume_source_invalid: progress schema/Git mismatch")
    bot = progress["bot"]
    if not isinstance(bot, dict):
        raise RecoveryError("resume_source_invalid: Bot identity missing")
    _keys(bot, {"basic_id", "bot_fp"}, "Bot")
    if bot["basic_id"] != expected_bot or not SHA256.fullmatch(str(bot["bot_fp"])):
        raise RecoveryError("resume_source_invalid: Bot identity mismatch")
    recovery = progress["recovery"]
    if not isinstance(recovery, dict):
        raise RecoveryError("resume_source_invalid: recovery identity missing")
    _keys(
        recovery,
        {
            "schema_version",
            "repository",
            "workflow",
            "run_id",
            "run_attempt",
            "operation",
            "created_at",
            "manifest_produced",
            "manifest_uploaded",
        },
        "recovery identity",
    )
    if (
        recovery["schema_version"] != 1
        or recovery["repository"] != REPOSITORY
        or recovery["workflow"] != WORKFLOW
        or recovery["run_id"] != source_run_id
        or recovery["run_attempt"] != source_attempt
        or recovery["operation"] != "publish"
        or recovery["manifest_produced"] is not manifest_produced
        or recovery["manifest_uploaded"] is not False
    ):
        raise RecoveryError("resume_source_invalid: recovery identity mismatch")
    created = _parse_time(recovery["created_at"])
    updated = _parse_time(progress["updated_at"])
    if (
        created < now - MAX_AGE
        or created > now + timedelta(minutes=5)
        or updated < now - MAX_AGE
        or updated > now + timedelta(minutes=5)
    ):
        raise RecoveryError("resume_source_invalid: progress expired")
    resources = progress["resources"]
    if not isinstance(resources, dict) or not resources:
        raise RecoveryError("resume_source_invalid: progress has no started resources")
    seen_roles: set[str] = set()
    seen_ids: set[str] = set()
    for fingerprint, record in resources.items():
        if not isinstance(record, dict) or not SHA256.fullmatch(str(fingerprint)):
            raise RecoveryError("resume_source_invalid: invalid resource record")
        allowed = {
            "role",
            "definition_sha256",
            "image_sha256",
            "stage",
            "verified",
            "id",
            "history",
        }
        if set(record) - allowed:
            raise RecoveryError("resume_source_invalid: unknown resource fields")
        role = record.get("role")
        if role not in ROLES or role in seen_roles or role not in plan:
            raise RecoveryError("resume_source_invalid: invalid or duplicate role")
        seen_roles.add(role)
        expected = plan[role]
        if (
            fingerprint != expected["fingerprint"]
            or record.get("definition_sha256") != expected["definition_sha256"]
            or record.get("image_sha256") != expected["image_sha256"]
        ):
            raise RecoveryError("resume_source_invalid: definition/image hash mismatch")
        resource_id = record.get("id")
        if resource_id is not None:
            if (
                not isinstance(resource_id, str)
                or not MENU_ID.fullmatch(resource_id)
                or resource_id in seen_ids
            ):
                raise RecoveryError("resume_source_invalid: invalid or duplicate candidate ID")
            seen_ids.add(resource_id)
        if record.get("stage") not in {
            "planned",
            "create_intent",
            "created",
            "verifying",
            "upload_pending",
            "verification_failed",
            "ready",
        } or not isinstance(record.get("verified"), bool):
            raise RecoveryError("resume_source_invalid: invalid resource state")
        history = record.get("history", [])
        if not isinstance(history, list):
            raise RecoveryError("resume_source_invalid: invalid resource history")
        for event in history:
            if not isinstance(event, dict) or set(event) != {"at", "stage"}:
                raise RecoveryError("resume_source_invalid: invalid resource history")
            _parse_time(event["at"])
            if not isinstance(event["stage"], str):
                raise RecoveryError("resume_source_invalid: invalid resource history")
        if manifest_produced and (
            resource_id is None or record["stage"] != "ready" or record["verified"] is not True
        ):
            raise RecoveryError("resume_source_invalid: incomplete stored-manifest candidate")
        record["verified"] = False
    if manifest_produced and seen_roles != set(ROLES):
        raise RecoveryError("resume_source_invalid: incomplete manifest roles")
    if not seen_ids:
        raise RecoveryError("resume_source_invalid: no resumable candidate")
    return progress


def validate_and_prepare(
    archive: bytes,
    *,
    archive_sha256: str,
    run: dict[str, Any],
    artifacts: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    plan: dict[str, dict],
    git_sha: str,
    expected_bot: str,
    source_run_id: str,
    current_run_id: str,
    current_attempt: str,
    now: datetime | None = None,
) -> bytes:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if not SHA256.fullmatch(archive_sha256) or sha256(archive).hexdigest() != archive_sha256:
        raise RecoveryError("resume_source_invalid: artifact digest mismatch")
    repository = run.get("repository")
    head_repository = run.get("head_repository")
    if (
        not isinstance(repository, dict)
        or repository.get("full_name") != REPOSITORY
        or not isinstance(head_repository, dict)
        or head_repository.get("full_name") != REPOSITORY
        or str(run.get("id")) != source_run_id
        or run.get("path") != WORKFLOW
        or run.get("event") != "workflow_dispatch"
        or run.get("head_sha") != git_sha
        or run.get("head_branch") != "release"
        or run.get("conclusion") == "success"
    ):
        raise RecoveryError("resume_source_invalid: source workflow metadata mismatch")
    source_attempt = str(run.get("run_attempt"))
    expected_name = f"line-rich-menu-publication-{git_sha}-{source_attempt}"
    matches = [item for item in artifacts if item.get("name") == expected_name]
    if (
        len(matches) != 1
        or matches[0].get("expired") is not False
        or matches[0].get("digest") != f"sha256:{archive_sha256}"
    ):
        raise RecoveryError("resume_artifact_unavailable: artifact identity invalid")
    if not any(
        job.get("name") == PUBLISH_JOB and job.get("conclusion") != "skipped" for job in jobs
    ):
        raise RecoveryError("resume_source_invalid: protected publish job was not entered")
    progress_raw, receipt_raw = _extract(archive)
    receipt = _json(receipt_raw, "receipt")
    required_receipt = {
        "schema_version",
        "operation",
        "workflow",
        "repository",
        "workflow_identity",
        "git_sha",
        "timestamp",
        "publication_config_sha256",
        "credential",
        "global_default_changed",
        "per_user_binding_changed",
        "resources_deleted",
        "status",
        "failure_gate",
        "orphan_candidate_ids",
        "verified_manifest_created",
        "manifest_uploaded",
        "progress_sha256",
        "error_code",
        "candidate_ids",
    }
    _keys(receipt, required_receipt, "receipt")
    if (
        receipt["schema_version"] != 1
        or receipt["operation"] != "menu-publication"
        or receipt["repository"] != REPOSITORY
        or receipt["workflow_identity"] != WORKFLOW
        or receipt["git_sha"] != git_sha
        or receipt["workflow"] != {"run_id": source_run_id, "run_attempt": source_attempt}
        or receipt["status"] != "failure"
        or not isinstance(receipt["verified_manifest_created"], bool)
        or (
            receipt["verified_manifest_created"]
            and receipt["failure_gate"] != "immutable_manifest_storage"
        )
        or receipt["manifest_uploaded"] is not False
        or not re.fullmatch(r"[0-9a-f]{64}", str(receipt["publication_config_sha256"]))
        or not isinstance(receipt["credential"], dict)
        or set(receipt["credential"]) != {"secret_name", "version"}
        or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_-]{0,254}", str(receipt["credential"]["secret_name"])
        )
        or not re.fullmatch(r"[1-9][0-9]*", str(receipt["credential"]["version"]))
        or receipt["progress_sha256"] != sha256(progress_raw).hexdigest()
        or any(
            receipt[key] is not False
            for key in ("global_default_changed", "per_user_binding_changed", "resources_deleted")
        )
    ):
        raise RecoveryError("resume_source_invalid: failure receipt mismatch")
    progress = _validate_progress(
        progress_raw,
        plan=plan,
        git_sha=git_sha,
        expected_bot=expected_bot,
        source_run_id=source_run_id,
        source_attempt=source_attempt,
        manifest_produced=receipt["verified_manifest_created"],
        now=now,
    )
    progress_ids = sorted(
        record["id"]
        for record in progress["resources"].values()
        if isinstance(record, dict)
        and isinstance(record.get("id"), str)
        and record.get("stage") != "ready"
    )
    if receipt["orphan_candidate_ids"] != progress_ids:
        raise RecoveryError("resume_source_invalid: receipt candidate mismatch")
    receipt_time = _parse_time(receipt["timestamp"])
    if receipt_time < now - MAX_AGE or receipt_time > now + timedelta(minutes=5):
        raise RecoveryError("resume_source_invalid: receipt expired")
    progress["recovery"] = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "workflow": WORKFLOW,
        "run_id": current_run_id,
        "run_attempt": current_attempt,
        "operation": "publish",
        "created_at": now.isoformat(),
        "manifest_produced": False,
        "manifest_uploaded": False,
    }
    progress["updated_at"] = now.isoformat()
    return canonical(progress)


class GitHubRecoveryClient:
    def __init__(self, client: httpx.Client):
        self.client = client

    def get_json(self, path: str) -> dict[str, Any]:
        try:
            response = self.client.get(f"https://api.github.com{path}", follow_redirects=False)
        except httpx.HTTPError as exc:
            raise RecoveryError("resume_artifact_unavailable: GitHub metadata unavailable") from exc
        if response.status_code != 200:
            raise RecoveryError("resume_artifact_unavailable: GitHub metadata unavailable")
        return _json(response.content, "GitHub metadata")

    def recover(
        self,
        *,
        source_run_id: str,
        archive_sha256: str,
        git_sha: str,
        expected_bot: str,
        current_run_id: str,
        current_attempt: str,
        plan: dict[str, dict],
    ) -> bytes:
        base = f"/repos/{REPOSITORY}/actions/runs/{source_run_id}"
        run = self.get_json(base)
        artifacts_doc = self.get_json(f"{base}/artifacts")
        jobs_doc = self.get_json(f"{base}/jobs")
        source_attempt = str(run.get("run_attempt"))
        expected_name = f"line-rich-menu-publication-{git_sha}-{source_attempt}"
        artifacts = artifacts_doc.get("artifacts")
        jobs = jobs_doc.get("jobs")
        if not isinstance(artifacts, list) or not isinstance(jobs, list):
            raise RecoveryError("resume_source_invalid: GitHub collection invalid")
        matches = [
            item
            for item in artifacts
            if isinstance(item, dict) and item.get("name") == expected_name
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
            raise RecoveryError("resume_artifact_unavailable: artifact missing or ambiguous")
        try:
            response = self.client.get(
                f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{matches[0]['id']}/zip",
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            raise RecoveryError("resume_artifact_unavailable: artifact download failed") from exc
        if response.status_code != 200:
            raise RecoveryError("resume_artifact_unavailable: artifact download failed")
        return validate_and_prepare(
            response.content,
            archive_sha256=archive_sha256,
            run=run,
            artifacts=artifacts,
            jobs=jobs,
            plan=plan,
            git_sha=git_sha,
            expected_bot=expected_bot,
            source_run_id=source_run_id,
            current_run_id=current_run_id,
            current_attempt=current_attempt,
        )


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".recovered-progress-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run-id")
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--expected-bot", required=True)
    parser.add_argument("--current-run-id", required=True)
    parser.add_argument("--current-run-attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pair = bool(args.source_run_id) == bool(args.artifact_sha256)
    if not pair:
        parser.error("resume inputs must be provided together")
    if not args.source_run_id:
        print("Fresh publication: no recovery artifact requested")
        return
    if (
        not RUN_ID.fullmatch(args.source_run_id)
        or not SHA256.fullmatch(args.artifact_sha256)
        or not SHA1.fullmatch(args.git_sha)
        or not BOT_ID.fullmatch(args.expected_bot)
        or not RUN_ID.fullmatch(args.current_run_id)
        or not RUN_ID.fullmatch(args.current_run_attempt)
    ):
        parser.error("resume identity is invalid")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        parser.error("GITHUB_TOKEN is required only for protected resume")
    definitions = discover_definitions()
    plan = publication_plan(
        {role: definitions[role] for role in sorted(ROLES)}, Path("infra/local/rich-menu-images")
    )
    try:
        with httpx.Client(
            timeout=20,
            trust_env=False,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        ) as client:
            content = GitHubRecoveryClient(client).recover(
                source_run_id=args.source_run_id,
                archive_sha256=args.artifact_sha256,
                git_sha=args.git_sha,
                expected_bot=args.expected_bot,
                current_run_id=args.current_run_id,
                current_attempt=args.current_run_attempt,
                plan=plan,
            )
        _atomic_write(args.output, content)
    except RecoveryError as exc:
        parser.exit(1, f"{exc}\nNo LINE or GCP operation performed.\n")
    print("Trusted publication progress restored; LINE readback is still required")


if __name__ == "__main__":
    main()
