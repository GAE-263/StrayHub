from __future__ import annotations

import io
import json
import stat
import zipfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx
import pytest
from scripts import sync_line_role_menus as menus
from scripts.line_menu_publication import PublicationError, ResourcePublisher, canonical
from scripts.line_menu_publication_gate import failure_receipt
from scripts.line_menu_publication_recovery import (
    PUBLISH_JOB,
    REPOSITORY,
    WORKFLOW,
    GitHubRecoveryClient,
    RecoveryError,
    validate_and_prepare,
)
from tests.unit.test_rich_menu_publication_safety import FakeLine

GIT_SHA = "a" * 40
BOT = "@synthetic"
SOURCE_RUN = "123"
SOURCE_ATTEMPT = "2"
NOW = datetime(2026, 9, 13, 6, 0, tzinfo=UTC)


@pytest.fixture
def plan() -> dict[str, dict]:
    definitions = menus.discover_definitions()
    return menus.publication_plan(
        {role: definitions[role] for role in ("default", "volunteer", "adoption_hub")},
        Path("infra/local/rich-menu-images"),
    )


def progress_document(plan: dict[str, dict]) -> dict:
    item = plan["default"]
    return {
        "schema": 1,
        "git_sha": GIT_SHA,
        "bot": {"basic_id": BOT, "bot_fp": sha256(b"synthetic-bot").hexdigest()},
        "resources": {
            item["fingerprint"]: {
                "role": "default",
                "definition_sha256": item["definition_sha256"],
                "image_sha256": item["image_sha256"],
                "stage": "upload_pending",
                "verified": False,
                "id": "richmenu-owned",
                "history": [{"at": NOW.isoformat(), "stage": "upload_pending"}],
            }
        },
        "updated_at": NOW.isoformat(),
        "recovery": {
            "schema_version": 1,
            "repository": REPOSITORY,
            "workflow": WORKFLOW,
            "run_id": SOURCE_RUN,
            "run_attempt": SOURCE_ATTEMPT,
            "operation": "publish",
            "created_at": NOW.isoformat(),
            "manifest_produced": False,
            "manifest_uploaded": False,
        },
    }


def archive_for(plan: dict[str, dict], *, progress: dict | None = None, extra=None) -> bytes:
    progress_raw = canonical(progress or progress_document(plan))
    scratch = Path("/tmp/not-used")
    receipt = failure_receipt(
        git_sha=GIT_SHA,
        failure_gate="resource_publication",
        progress_path=scratch,
        run_id=SOURCE_RUN,
        run_attempt=SOURCE_ATTEMPT,
    )
    receipt["progress_sha256"] = sha256(progress_raw).hexdigest()
    document = progress or progress_document(plan)
    receipt["orphan_candidate_ids"] = sorted(
        record["id"] for record in document["resources"].values() if "id" in record
    )
    receipt["timestamp"] = NOW.isoformat()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        bundle.writestr("progress.json", progress_raw)
        bundle.writestr("receipt.json", canonical(receipt))
        if extra:
            name, value = extra
            bundle.writestr(name, value)
    return stream.getvalue()


def metadata(archive: bytes) -> tuple[dict, list[dict], list[dict]]:
    digest = sha256(archive).hexdigest()
    run = {
        "id": int(SOURCE_RUN),
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
        "path": WORKFLOW,
        "event": "workflow_dispatch",
        "head_sha": GIT_SHA,
        "head_branch": "release",
        "run_attempt": int(SOURCE_ATTEMPT),
        "conclusion": "failure",
    }
    artifacts = [
        {
            "name": f"line-rich-menu-publication-{GIT_SHA}-{SOURCE_ATTEMPT}",
            "expired": False,
            "digest": f"sha256:{digest}",
        }
    ]
    jobs = [{"name": PUBLISH_JOB, "conclusion": "failure"}]
    return run, artifacts, jobs


def validate(archive: bytes, plan: dict[str, dict], **overrides) -> bytes:
    run, artifacts, jobs = metadata(archive)
    values = {
        "archive_sha256": sha256(archive).hexdigest(),
        "run": run,
        "artifacts": artifacts,
        "jobs": jobs,
        "plan": plan,
        "git_sha": GIT_SHA,
        "expected_bot": BOT,
        "source_run_id": SOURCE_RUN,
        "current_run_id": "456",
        "current_attempt": "1",
        "now": NOW,
    }
    values.update(overrides)
    return validate_and_prepare(archive, **values)


@pytest.mark.asyncio
async def test_valid_resume_reuses_owned_candidate_and_uploads_once(plan, tmp_path):
    archive = archive_for(plan)
    recovered = validate(archive, plan)
    progress = json.loads(recovered)
    path = tmp_path / "progress.json"
    path.write_bytes(recovered)

    fake = FakeLine()
    fake.resources = {"richmenu-owned": plan["default"]["definition"]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)) as client:
        result = await ResourcePublisher(client).publish(
            {"default": plan["default"]},
            path,
            BOT,
            GIT_SHA,
            recovery_identity=progress["recovery"],
        )

    assert result == {"default": "richmenu-owned"}
    assert fake.calls.count(("POST", "richmenu")) == 0
    assert fake.calls.count(("POST", "richmenu/richmenu-owned/content")) == 1


@pytest.mark.asyncio
async def test_valid_resume_with_complete_image_performs_no_write(plan, tmp_path):
    recovered = validate(archive_for(plan), plan)
    progress = json.loads(recovered)
    path = tmp_path / "progress.json"
    path.write_bytes(recovered)
    fake = FakeLine()
    fake.resources = {"richmenu-owned": plan["default"]["definition"]}
    fake.images = {"richmenu-owned": plan["default"]["image"]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)) as client:
        await ResourcePublisher(client).publish(
            {"default": plan["default"]},
            path,
            BOT,
            GIT_SHA,
            recovery_identity=progress["recovery"],
        )
    assert all(method == "GET" for method, _ in fake.calls)


@pytest.mark.asyncio
async def test_all_resume_candidates_are_read_back_before_first_write(plan, tmp_path):
    progress = progress_document(plan)
    second = plan["volunteer"]
    progress["resources"][second["fingerprint"]] = {
        "role": "volunteer",
        "definition_sha256": second["definition_sha256"],
        "image_sha256": second["image_sha256"],
        "stage": "upload_pending",
        "verified": False,
        "id": "richmenu-second",
        "history": [],
    }
    recovered = validate(archive_for(plan, progress=progress), plan)
    state = json.loads(recovered)
    path = tmp_path / "progress.json"
    path.write_bytes(recovered)
    fake = FakeLine()
    fake.resources = {
        "richmenu-owned": plan["default"]["definition"],
        "richmenu-second": second["definition"],
    }
    fake.images = {"richmenu-second": b"wrong-image"}
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)) as client:
        with pytest.raises(PublicationError, match="image mismatch"):
            await ResourcePublisher(client).publish(
                {"default": plan["default"], "volunteer": second},
                path,
                BOT,
                GIT_SHA,
                recovery_identity=state["recovery"],
            )
    assert all(method == "GET" for method, _ in fake.calls)


@pytest.mark.parametrize(
    "mutation",
    [
        "repository",
        "workflow",
        "event",
        "git_sha",
        "ref",
        "operation",
        "bot",
        "definition",
        "image",
        "candidate_duplicate",
        "expired",
        "artifact_name",
        "artifact_digest",
        "missing_artifact",
        "publish_job",
        "success_run",
    ],
)
def test_invalid_recovery_sources_fail_before_any_line_transport(plan, mutation):
    progress = progress_document(plan)
    if mutation == "operation":
        progress["recovery"]["operation"] = "plan"
    elif mutation == "bot":
        progress["bot"]["basic_id"] = "@other"
    elif mutation == "definition":
        next(iter(progress["resources"].values()))["definition_sha256"] = "b" * 64
    elif mutation == "image":
        next(iter(progress["resources"].values()))["image_sha256"] = "b" * 64
    elif mutation == "candidate_duplicate":
        item = plan["volunteer"]
        progress["resources"][item["fingerprint"]] = {
            "role": "volunteer",
            "definition_sha256": item["definition_sha256"],
            "image_sha256": item["image_sha256"],
            "stage": "created",
            "verified": False,
            "id": "richmenu-owned",
            "history": [],
        }
    elif mutation == "expired":
        progress["updated_at"] = "2020-01-01T00:00:00+00:00"
    archive = archive_for(plan, progress=progress)
    run, artifacts, jobs = metadata(archive)
    if mutation == "repository":
        run["repository"]["full_name"] = "other/repo"
    elif mutation == "workflow":
        run["path"] = ".github/workflows/other.yml"
    elif mutation == "event":
        run["event"] = "push"
    elif mutation == "git_sha":
        run["head_sha"] = "b" * 40
    elif mutation == "ref":
        run["head_branch"] = "main"
    elif mutation == "artifact_name":
        artifacts[0]["name"] = "attacker-controlled"
    elif mutation == "artifact_digest":
        artifacts[0]["digest"] = "sha256:" + "b" * 64
    elif mutation == "missing_artifact":
        artifacts.clear()
    elif mutation == "publish_job":
        jobs[0]["conclusion"] = "skipped"
    elif mutation == "success_run":
        run["conclusion"] = "success"
    with pytest.raises(RecoveryError):
        validate(
            archive,
            plan,
            run=run,
            artifacts=artifacts,
            jobs=jobs,
            archive_sha256=sha256(archive).hexdigest(),
        )


@pytest.mark.parametrize("extra", [("../progress.json", b"x"), ("extra.json", b"x")])
def test_archive_rejects_traversal_and_extra_members(plan, extra):
    archive = archive_for(plan, extra=extra)
    with pytest.raises(RecoveryError, match="artifact"):
        validate(archive, plan)


def test_archive_rejects_symlink(plan):
    progress_raw = canonical(progress_document(plan))
    receipt_archive = archive_for(plan)
    with zipfile.ZipFile(io.BytesIO(receipt_archive)) as source:
        receipt_raw = source.read("receipt.json")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        info = zipfile.ZipInfo("progress.json")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, progress_raw)
        bundle.writestr("receipt.json", receipt_raw)
    with pytest.raises(RecoveryError, match="unsafe"):
        validate(stream.getvalue(), plan)


def test_duplicate_json_keys_are_rejected(plan):
    archive = archive_for(plan)
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        receipt = json.loads(source.read("receipt.json"))
    bad = b'{"schema":1,"schema":1}'
    receipt["progress_sha256"] = sha256(bad).hexdigest()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        bundle.writestr("progress.json", bad)
        bundle.writestr("receipt.json", canonical(receipt))
    with pytest.raises(RecoveryError, match="duplicate JSON key"):
        validate(stream.getvalue(), plan)


def test_github_adapter_uses_fixed_repository_paths_and_downloads_verified_artifact(plan):
    archive = archive_for(plan)
    run, artifacts, jobs = metadata(archive)
    artifacts[0]["id"] = 987
    calls: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        responses = {
            f"/repos/{REPOSITORY}/actions/runs/{SOURCE_RUN}": run,
            f"/repos/{REPOSITORY}/actions/runs/{SOURCE_RUN}/artifacts": {"artifacts": artifacts},
            f"/repos/{REPOSITORY}/actions/runs/{SOURCE_RUN}/jobs": {"jobs": jobs},
        }
        if request.url.path == f"/repos/{REPOSITORY}/actions/artifacts/987/zip":
            return httpx.Response(200, content=archive)
        return httpx.Response(200, json=responses[request.url.path])

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        recovered = GitHubRecoveryClient(client).recover(
            source_run_id=SOURCE_RUN,
            archive_sha256=sha256(archive).hexdigest(),
            git_sha=GIT_SHA,
            expected_bot=BOT,
            current_run_id="456",
            current_attempt="1",
            plan=plan,
        )
    assert json.loads(recovered)["recovery"]["run_id"] == "456"
    assert calls[-1] == f"/repos/{REPOSITORY}/actions/artifacts/987/zip"
    assert all(path.startswith(f"/repos/{REPOSITORY}/actions/") for path in calls)


def test_github_adapter_download_failure_is_explicit(plan):
    archive = archive_for(plan)
    run, artifacts, jobs = metadata(archive)
    artifacts[0]["id"] = 987

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/zip"):
            return httpx.Response(503)
        if request.url.path.endswith("/artifacts"):
            return httpx.Response(200, json={"artifacts": artifacts})
        if request.url.path.endswith("/jobs"):
            return httpx.Response(200, json={"jobs": jobs})
        return httpx.Response(200, json=run)

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(RecoveryError, match="download failed"):
            GitHubRecoveryClient(client).recover(
                source_run_id=SOURCE_RUN,
                archive_sha256=sha256(archive).hexdigest(),
                git_sha=GIT_SHA,
                expected_bot=BOT,
                current_run_id="456",
                current_attempt="1",
                plan=plan,
            )
