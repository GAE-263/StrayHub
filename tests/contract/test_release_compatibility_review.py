"""Exact predecessor binding for tooling-only rollback approval."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "compat_manifest", ROOT / "infra/gce/scripts/release-manifest.py"
)
assert SPEC and SPEC.loader
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def review_repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    git(tmp_path, "config", "user.name", "Synthetic")
    (tmp_path / "app.py").write_text("original\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    sha = git(tmp_path, "rev-parse", "HEAD")
    previous = {
        "git_sha": sha,
        "release_id": f"20260915T154252Z-{sha[:12]}",
        "manifest_sha256": "a" * 64,
        "migration_revision": "revision_7",
    }
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "unchanged-runtime",
                "reason": "reviewed tooling change",
                "previous": previous,
            }
        )
    )
    return tmp_path, review, previous


def test_unchanged_runtime_review_is_bound_to_exact_predecessor(review_repo):
    root, review, previous = review_repo
    assert tool.reviewed_predecessor(review, root, "revision_7") == previous
    path = root / "infra/gce/scripts/deployment-state.py"
    path.parent.mkdir(parents=True)
    path.write_text("# deployment tooling\n")
    git(root, "add", str(path))
    git(root, "commit", "-qm", "tooling")
    assert tool.reviewed_predecessor(review, root, "revision_7") == previous


@pytest.mark.parametrize(
    "name",
    [
        "app.py",
        "uv.lock",
        "services/api/migrations/versions/new.py",
        "infra/gce/docker-compose.production.yml",
        "new-runtime-file",
    ],
)
def test_any_unreviewed_runtime_change_refuses_compatibility(review_repo, name):
    root, review, _ = review_repo
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("changed\n")
    git(root, "add", str(path))
    git(root, "commit", "-qm", "runtime change")
    with pytest.raises(tool.ReleaseError, match="runtime changed"):
        tool.reviewed_predecessor(review, root, "revision_7")


def test_migration_and_predecessor_identity_must_match(review_repo):
    root, review, previous = review_repo
    with pytest.raises(tool.ReleaseError, match="migration mismatch"):
        tool.reviewed_predecessor(review, root, "different_revision")
    with pytest.raises(tool.ReleaseError, match="identity"):
        tool.validate_predecessor_identity(previous | {"git_sha": "b" * 40})


def test_unavailable_predecessor_history_refuses_review(review_repo):
    root, review, previous = review_repo
    data = json.loads(review.read_text())
    data["previous"] = previous | {
        "git_sha": "b" * 40,
        "release_id": "20260915T154252Z-" + "b" * 12,
    }
    review.write_text(json.dumps(data))
    with pytest.raises(tool.ReleaseError, match="Git tree is unavailable"):
        tool.reviewed_predecessor(review, root, "revision_7")


def test_live_previous_manifest_is_matched_by_full_identity_and_checksum(tmp_path, monkeypatch):
    previous_path = tmp_path / "previous.json"
    previous = {
        "git_sha": "b" * 40,
        "release_id": "20260915T000000Z-" + "b" * 12,
        "migration_revision": "revision_7",
    }
    previous_path.write_text(json.dumps(previous))
    binding = previous | {"manifest_sha256": tool.sha256_file(previous_path)}
    candidate = tmp_path / "candidate.json"
    monkeypatch.setattr(
        tool,
        "load_manifest",
        lambda path: (
            {"rollback_predecessor": binding} if path == candidate else json.loads(path.read_text())
        ),
    )
    tool.validate_predecessor(candidate, previous_path)
    previous_path.write_text(previous_path.read_text() + "\n")
    with pytest.raises(tool.ReleaseError, match="predecessor mismatch"):
        tool.validate_predecessor(candidate, previous_path)
