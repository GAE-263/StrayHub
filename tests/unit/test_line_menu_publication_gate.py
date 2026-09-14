from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts.line_menu_manifest import (
    finalize_publication_manifest,
    load_publication_manifest,
)
from scripts.line_menu_publication import PublicationError
from scripts.line_menu_publication_gate import (
    GcloudImmutableStore,
    ImmutableStorageError,
    StoredObject,
    failure_receipt,
    read_token_file,
    run_gate,
    success_receipt,
)
from tests.unit.test_line_menu_manifest import BOT, GIT_SHA, manifest_document, write_manifest


def test_final_manifest_is_deterministic_and_uses_authoritative_schema(tmp_path: Path) -> None:
    first_progress = manifest_document(staff=True)
    second_progress = manifest_document(staff=True)
    first_progress["updated_at"] = "2026-09-13T01:00:00+00:00"
    second_progress["updated_at"] = "2026-09-13T02:00:00+00:00"
    for record in second_progress["resources"].values():
        record["history"] = [{"at": "later", "stage": "ready"}]

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    finalize_publication_manifest(
        write_manifest(tmp_path / "first-progress.json", first_progress),
        first,
        expected_git_sha=GIT_SHA,
        expected_bot_basic_id=BOT,
    )
    finalize_publication_manifest(
        write_manifest(tmp_path / "second-progress.json", second_progress),
        second,
        expected_git_sha=GIT_SHA,
        expected_bot_basic_id=BOT,
    )

    assert first.read_bytes() == second.read_bytes()
    verified = load_publication_manifest(first, expected_git_sha=GIT_SHA, expected_bot_basic_id=BOT)
    assert verified.manifest_sha256
    document = json.loads(first.read_bytes())
    assert set(document) == {"schema", "git_sha", "bot", "resources"}
    assert {record["role"] for record in document["resources"].values()} == {
        "default",
        "volunteer",
        "adoption_hub",
    }
    assert all("history" not in record for record in document["resources"].values())


class FakeGcloud:
    def __init__(self, existing: bytes | None = None):
        self.content = existing
        self.calls: list[list[str]] = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        if args[1:3] == ["storage", "cp"]:
            candidate = Path(args[3]).read_bytes()
            if self.content is not None:
                return subprocess.CompletedProcess(args, 1, b"", b"already exists")
            self.content = candidate
            return subprocess.CompletedProcess(args, 0, b"", b"")
        if args[1:3] == ["storage", "cat"]:
            if self.content is None:
                return subprocess.CompletedProcess(args, 1, b"", b"missing")
            return subprocess.CompletedProcess(args, 0, self.content, b"")
        if args[1:4] == ["storage", "objects", "describe"]:
            return subprocess.CompletedProcess(args, 0, b'{"generation":"42"}', b"")
        raise AssertionError(args)


def test_immutable_store_uses_create_only_and_verifies_readback() -> None:
    fake = FakeGcloud()
    store = GcloudImmutableStore("synthetic-menu-manifests", runner=fake)

    first = store.put("line-rich-menu-manifests", b'{"schema":1}')
    second = store.put("line-rich-menu-manifests", b'{"schema":1}')

    assert first.created is True and second.created is False
    assert first.uri == second.uri
    cp_calls = [call for call in fake.calls if call[1:3] == ["storage", "cp"]]
    assert all("--if-generation-match=0" in call for call in cp_calls)
    assert all("latest" not in " ".join(call) for call in fake.calls)


def test_immutable_store_rejects_existing_object_with_different_content() -> None:
    store = GcloudImmutableStore("synthetic-menu-manifests", runner=FakeGcloud(b"different"))

    with pytest.raises(ImmutableStorageError, match="readback mismatch"):
        store.put("line-rich-menu-manifests", b'{"schema":1}')


def test_success_receipt_is_sanitized_and_staff_is_not_claimed(tmp_path: Path) -> None:
    final = tmp_path / "verified.json"
    verified = finalize_publication_manifest(
        write_manifest(tmp_path / "progress.json", manifest_document(staff=True)),
        final,
        expected_git_sha=GIT_SHA,
        expected_bot_basic_id=BOT,
    )
    receipt = success_receipt(
        verified=verified,
        outcomes={role: "reused" for role in verified.menus},
        stored=StoredObject(
            uri="gs://synthetic/line-rich-menu-manifests/hash.json",
            generation="42",
            created=False,
        ),
        run_id="123",
        run_attempt="1",
    )
    serialized = json.dumps(receipt)

    assert set(receipt["menus"]) == {"default", "volunteer", "adoption_hub"}
    assert receipt["global_default_changed"] is False
    assert receipt["per_user_binding_changed"] is False
    assert receipt["resources_deleted"] is False
    assert "token" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert "staff" not in serialized.lower()


def test_failure_receipt_records_orphan_without_secret(tmp_path: Path) -> None:
    progress = manifest_document()
    record = next(iter(progress["resources"].values()))
    record.update(id="richmenu-synthetic-orphan", stage="upload_pending", verified=False)
    path = write_manifest(tmp_path / "progress.json", progress)

    receipt = failure_receipt(
        git_sha=GIT_SHA,
        failure_gate="resource_publication",
        progress_path=path,
        run_id="123",
        run_attempt="1",
    )

    assert receipt["orphan_candidate_ids"] == ["richmenu-synthetic-orphan"]
    assert receipt["manifest_uploaded"] is False
    assert receipt["global_default_changed"] is False
    serialized = json.dumps(receipt).lower()
    assert receipt["credential"] == {"secret_name": "synthetic-secret", "version": "1"}
    assert "access_token" not in serialized
    assert "authorization" not in serialized


class FakePublisher:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.outcomes = {role: "reused" for role in ("default", "volunteer", "adoption_hub")}

    async def publish(self, plan, progress_path, expected_bot, git_sha):
        document = manifest_document()
        if self.fail:
            record = next(iter(document["resources"].values()))
            record.update(id="richmenu-synthetic-orphan", stage="upload_pending", verified=False)
        write_manifest(progress_path, document)
        if self.fail:
            raise PublicationError("synthetic failure")
        return {role: values["id"] for role, values in _records_by_role(document).items()}


def _records_by_role(document: dict) -> dict:
    return {record["role"]: record for record in document["resources"].values()}


class FakeStore:
    def __init__(self):
        self.objects = []

    def put(self, namespace, content):
        self.objects.append((namespace, content))
        return StoredObject(
            uri=f"gs://synthetic/{namespace}/{len(self.objects)}.json",
            generation=str(len(self.objects)),
            created=True,
        )


@pytest.mark.asyncio
async def test_gate_validates_then_stores_manifest_and_receipt(tmp_path: Path) -> None:
    store = FakeStore()

    receipt = await run_gate(
        publisher=FakePublisher(),
        plan={},
        progress_path=tmp_path / "progress.json",
        final_path=tmp_path / "verified.json",
        receipt_path=tmp_path / "receipt.json",
        expected_bot=BOT,
        git_sha=GIT_SHA,
        store=store,
        run_id="123",
        run_attempt="1",
    )

    assert receipt["status"] == "success"
    assert [namespace for namespace, _ in store.objects] == [
        "line-rich-menu-manifests",
        "line-rich-menu-receipts",
    ]
    assert json.loads(store.objects[0][1])["schema"] == 1
    assert store.objects[1][1] == (tmp_path / "receipt.json").read_bytes()


@pytest.mark.asyncio
async def test_partial_publication_has_failure_receipt_and_no_verified_manifest(
    tmp_path: Path,
) -> None:
    store = FakeStore()
    receipt_path = tmp_path / "receipt.json"

    with pytest.raises(PublicationError, match="resource_publication"):
        await run_gate(
            publisher=FakePublisher(fail=True),
            plan={},
            progress_path=tmp_path / "progress.json",
            final_path=tmp_path / "verified.json",
            receipt_path=receipt_path,
            expected_bot=BOT,
            git_sha=GIT_SHA,
            store=store,
            run_id="123",
            run_attempt="1",
        )

    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["failure_gate"] == "resource_publication"
    assert receipt["orphan_candidate_ids"] == ["richmenu-synthetic-orphan"]
    assert receipt["verified_manifest_created"] is False
    assert receipt["manifest_uploaded"] is False
    assert not (tmp_path / "verified.json").exists()
    assert store.objects == []


def test_storage_namespace_and_bucket_are_fail_closed() -> None:
    with pytest.raises(ImmutableStorageError):
        GcloudImmutableStore("INVALID BUCKET")
    with pytest.raises(ImmutableStorageError, match="namespace"):
        GcloudImmutableStore("synthetic-menu-manifests", runner=FakeGcloud()).put("latest", b"{}")


def test_publication_errors_are_safe_for_operator_output() -> None:
    error = PublicationError("Publication stopped at resource_publication")
    assert "token" not in str(error).lower()


def test_token_file_requires_mode_0600_and_single_line(tmp_path: Path) -> None:
    path = tmp_path / "token"
    path.write_text("synthetic-value", encoding="utf-8")
    path.chmod(0o600)
    assert read_token_file(path) == "synthetic-value"
    path.chmod(0o644)
    with pytest.raises(PublicationError, match="0600"):
        read_token_file(path)
    path.chmod(0o600)
    path.write_text("synthetic\nvalue", encoding="utf-8")
    with pytest.raises(PublicationError, match="single line"):
        read_token_file(path)
