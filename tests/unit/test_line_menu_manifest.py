from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.line_menu_manifest import MenuManifestError, load_publication_manifest

GIT_SHA = "a" * 40
BOT = "@synthetic-bot"


def manifest_document(*, staff: bool = False) -> dict:
    resources = {}
    roles = ["default", "volunteer", "adoption_hub"]
    if staff:
        roles.append("staff")
    for index, role in enumerate(roles, start=1):
        fingerprint = f"{index:x}" * 64
        resources[fingerprint] = {
            "role": role,
            "definition_sha256": f"{index + 5:x}" * 64,
            "image_sha256": f"{index + 9:x}" * 64,
            "stage": "ready",
            "verified": True,
            "id": f"richmenu-synthetic-{role.replace('_', '-')}",
            "history": [{"at": "2026-09-13T00:00:00+00:00", "stage": "ready"}],
        }
    return {
        "schema": 1,
        "git_sha": GIT_SHA,
        "bot": {"basic_id": BOT, "bot_fp": "b" * 64},
        "resources": resources,
        "updated_at": "2026-09-13T00:00:00+00:00",
    }


def write_manifest(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def load(path: Path):
    return load_publication_manifest(path, expected_git_sha=GIT_SHA, expected_bot_basic_id=BOT)


def test_complete_verified_manifest_is_accepted(tmp_path: Path) -> None:
    result = load(write_manifest(tmp_path / "manifest.json", manifest_document()))

    assert result.git_sha == GIT_SHA
    assert tuple(result.menus) == ("default", "volunteer", "adoption_hub")
    assert result.manifest_sha256


@pytest.mark.parametrize("role", ["default", "volunteer", "adoption_hub"])
def test_required_role_must_be_present_ready_and_verified(tmp_path: Path, role: str) -> None:
    document = manifest_document()
    record = next(value for value in document["resources"].values() if value["role"] == role)
    record["verified"] = False

    with pytest.raises(MenuManifestError, match="not ready"):
        load(write_manifest(tmp_path / "manifest.json", document))


def test_missing_role_and_unknown_schema_are_rejected(tmp_path: Path) -> None:
    document = manifest_document()
    fingerprint = next(
        key for key, value in document["resources"].items() if value["role"] == "volunteer"
    )
    del document["resources"][fingerprint]
    with pytest.raises(MenuManifestError, match="missing ready roles"):
        load(write_manifest(tmp_path / "manifest.json", document))

    document = manifest_document()
    document["schema"] = 2
    with pytest.raises(MenuManifestError, match="unsupported"):
        load(write_manifest(tmp_path / "manifest.json", document))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "not-a-menu", "ID is invalid"),
        ("definition_sha256", "short", "definition hash"),
        ("image_sha256", "short", "image hash"),
    ],
)
def test_resource_identity_formats_are_strict(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    document = manifest_document()
    next(iter(document["resources"].values()))[field] = value

    with pytest.raises(MenuManifestError, match=message):
        load(write_manifest(tmp_path / "manifest.json", document))


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"schema":1,"schema":1}', encoding="utf-8")

    with pytest.raises(MenuManifestError, match="duplicate JSON key"):
        load(path)


@pytest.mark.parametrize("mismatch", ["git", "bot"])
def test_manifest_identity_mismatch_is_rejected(tmp_path: Path, mismatch: str) -> None:
    document = manifest_document()
    if mismatch == "git":
        document["git_sha"] = "c" * 40
    else:
        document["bot"]["basic_id"] = "@other-bot"

    with pytest.raises(MenuManifestError, match="mismatch"):
        load(write_manifest(tmp_path / "manifest.json", document))


def test_staff_is_optional_and_never_promoted_by_validator(tmp_path: Path) -> None:
    result = load(write_manifest(tmp_path / "manifest.json", manifest_document(staff=True)))

    assert "staff" not in result.menus


def test_duplicate_required_role_or_resource_id_is_rejected(tmp_path: Path) -> None:
    document = manifest_document()
    records = list(document["resources"].values())
    records[1]["role"] = "default"
    with pytest.raises(MenuManifestError, match="duplicate role"):
        load(write_manifest(tmp_path / "manifest.json", document))

    document = manifest_document()
    records = list(document["resources"].values())
    records[1]["id"] = records[0]["id"]
    with pytest.raises(MenuManifestError, match="distinct resources"):
        load(write_manifest(tmp_path / "manifest.json", document))


def test_repository_cli_uses_the_same_validator(tmp_path: Path) -> None:
    path = write_manifest(tmp_path / "manifest.json", manifest_document())
    result = subprocess.run(
        [
            sys.executable,
            "infra/gce/scripts/verify-line-menu-manifest.py",
            "--manifest",
            str(path),
            "--expected-git-sha",
            GIT_SHA,
            "--expected-bot",
            BOT,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["validation"] == "passed"
