"""Durable recovery decisions and no mutation on ambiguous migration outcomes."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "deployment_state", ROOT / "infra/gce/scripts/deployment-state.py"
)
assert SPEC and SPEC.loader
state_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state_tool)
NEW = "20260910T000000Z-" + "a" * 12
OLD = "20260909T000000Z-" + "b" * 12


@pytest.fixture
def recovery(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    old = tmp_path / "releases" / OLD
    old.mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(old)
    old_manifest = {
        "release_id": OLD,
        "git_sha": "b" * 40,
        "images": {"api": "old"},
        "migration_revision": "head",
    }
    (old / "release-manifest.json").write_text(json.dumps(old_manifest))
    (state / "current.json").write_text(json.dumps(old_manifest | {"verification": "passed"}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(old_manifest | {"release_id": NEW, "git_sha": "a" * 40}))
    assert state_tool.plan(manifest, state, current, False) == ("prepare", OLD)
    return manifest, state, current


@pytest.mark.parametrize("stage", state_tool.STAGES)
@pytest.mark.parametrize("switched", [False, True])
def test_resume_decision_never_replays_ambiguous_migration(recovery, stage, switched):
    manifest, state, current = recovery
    journal = state / f"{NEW}.checkpoint.json"
    data = state_tool.read(journal)
    state_tool.atomic(journal, data | {"stage": stage})
    if switched:
        current.unlink()
        current.symlink_to(current.parent / "releases" / NEW)
    if switched and stage in state_tool.STAGES[9:]:
        assert state_tool.plan(manifest, state, current, True) == ("verify", OLD)
    elif not switched and stage in state_tool.PRE_MIGRATION:
        assert state_tool.plan(manifest, state, current, True) == ("prepare", OLD)
    else:
        with pytest.raises(ValueError, match="manual investigation"):
            state_tool.plan(manifest, state, current, True)


def test_artifact_drift_and_concurrent_release_fail_closed(recovery):
    manifest, state, current = recovery
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(ValueError, match="identity mismatch"):
        state_tool.plan(manifest, state, current, True)
    state_tool.atomic(state / "active-deployment.json", {"release_id": OLD})
    with pytest.raises(ValueError, match="another deployment"):
        state_tool.plan(manifest, state, current, True)


def test_atomic_checkpoint_rejects_symlink_and_contains_no_credentials(recovery, tmp_path):
    _, state, _ = recovery
    checkpoint = state / f"{NEW}.checkpoint.json"
    assert set(state_tool.read(checkpoint)) == {
        "schema_version",
        "release_id",
        "manifest_sha256",
        "previous_release_id",
        "stage",
    }
    target = tmp_path / "preserved"
    target.write_text("preserved")
    link = state / "symlink"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        state_tool.atomic(link, {})
    assert target.read_text() == "preserved"
    assert checkpoint.stat().st_mode & 0o777 == 0o600


def test_status_reports_pointer_receipt_gap_without_writes(recovery):
    manifest, state, current = recovery
    current.unlink()
    current.symlink_to(current.parent / "releases" / NEW)
    before = {p.name: p.read_bytes() for p in state.iterdir()}
    result = subprocess.run(
        [
            os.sys.executable,
            str(ROOT / "infra/gce/scripts/deployment-state.py"),
            "status",
            "--manifest",
            str(manifest),
            "--state-dir",
            str(state),
            "--current-link",
            str(current),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout)["deployed_without_receipt"] is True
    assert before == {p.name: p.read_bytes() for p in state.iterdir()}


@pytest.mark.parametrize(
    "script", ["deploy-release.sh", "rollback-release.sh", "rollforward-release.sh"]
)
def test_host_operations_share_lock_before_mutation(script):
    text = (ROOT / "infra/gce/scripts" / script).read_text()
    assert 'exec 9>"$STATE_DIR/.operation.lock"' in text
    assert text.index("flock -n 9") < text.index("systemctl stop")
    if script != "deploy-release.sh":
        assert "active-deployment.json" in text
        assert text.count("validate-receipt") == 2
        assert "strayhub-secrets.service strayhub-migrate.service" in text
        assert "--profile tools run --rm migration" not in text


@pytest.mark.parametrize(
    "output,valid",
    [
        ("INFO alembic\nrevision_7 (head)\n", True),
        ("prefix_revision_7 (head)\n", False),
        ("revision_7 (head)\nother (head)\n", False),
        ("revision_7\n", False),
    ],
)
def test_exact_single_database_head(output, valid):
    result = subprocess.run(
        [
            os.sys.executable,
            str(ROOT / "infra/gce/scripts/deployment-state.py"),
            "head",
            "--revision",
            "revision_7",
        ],
        input=output,
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == valid


@pytest.mark.parametrize("script", ["rollback-release.sh", "rollforward-release.sh"])
@pytest.mark.parametrize(
    "inactive", ["strayhub-secrets.service", "strayhub-migrate.service", "none"]
)
def test_each_dependency_must_be_active(script, inactive):
    text = (ROOT / "infra/gce/scripts" / script).read_text()
    start = text.index("for dependency in ")
    end = text.index("\ndone", start) + len("\ndone")
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'fail() { exit 7; }; systemctl() { [[ "$3" != "$INACTIVE" ]]; };\n' + text[start:end],
        ],
        env={"INACTIVE": inactive},
        capture_output=True,
        text=True,
    )
    assert result.returncode == (0 if inactive == "none" else 7)
