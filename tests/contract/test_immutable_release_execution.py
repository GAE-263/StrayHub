"""Execute real release/bundle scripts with a simulated registry and Docker CLI."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = "asia-east1-docker.pkg.dev/example-project/strayhub"

CLI = r"""#!/usr/bin/env python3
import json, os, pathlib, shutil, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
a = sys.argv[1:]
state = pathlib.Path(os.environ['FAKE_STATE'])
if name == 'git':
    a = a[2:] if a[:1] == ['-C'] else a
    if a[:1] == ['status']:
        sys.exit(0)
    sys.exit(subprocess.call([os.environ['REAL_GIT'], '-C', os.environ['REAL_ROOT'], *a]))
with (state / 'calls').open('a') as f:
    f.write(json.dumps([name, *a]) + '\n')
db = state / 'tags.json'
tags = json.loads(db.read_text()) if db.exists() else {}
if name == 'gcloud':
    if os.environ.get('EMPTY_DIGEST'):
        sys.exit(0)
    error = os.environ.get('LOOKUP_ERROR')
    if os.environ.get('LOOKUP_SERVICE') and os.environ['LOOKUP_SERVICE'] not in a[4]:
        error = None
    if error:
        print(error, file=sys.stderr)
        sys.exit(1)
    tag = a[4]
    if tag not in tags:
        print('NOT_FOUND: image absent', file=sys.stderr)
        sys.exit(1)
    print(tags[tag])
elif a[:2] == ['buildx', 'build']:
    tag = a[a.index('--tag') + 1]
    if os.environ.get('FAIL_BUILD') and os.environ['FAIL_BUILD'] in tag:
        sys.exit(1)
    tags[tag] = 'sha256:' + str(len(tags) + 1) * 64
    db.write_text(json.dumps(tags))
    if '/strayhub-release:' in tag:
        shutil.copytree(a[-1], state / 'artifact')
    print('build output must not contaminate image reference')
elif a[:1] == ['create']:
    assert '@sha256:' in a[1] and len(a) == 3
    print('fake-container')
elif a[:1] == ['cp']:
    shutil.copyfile(state / 'artifact' / a[1].split('/')[-1], a[2])
elif a[:1] == ['pull']:
    assert '@sha256:' in a[1]
elif a[:1] != ['rm']:
    raise SystemExit('unexpected docker invocation')
"""


@pytest.fixture
def release_cli(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    archive = subprocess.check_output(["git", "archive", "HEAD"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(source, filter="data")
    for script in ("build-immutable-release.sh", "build-release-bundle.sh"):
        shutil.copy2(ROOT / "scripts" / script, source / "scripts" / script)
    state = tmp_path / "state"
    state.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for command in ("git", "gcloud", "docker"):
        path = bin_dir / command
        path.write_text(CLI)
        path.chmod(0o755)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "REAL_GIT": str(shutil.which("git")),
        "REAL_ROOT": str(ROOT),
        "FAKE_STATE": str(state),
        "GITHUB_RUN_ID": "123",
    }

    def run(label: str, *args: str, **extra_env: str):
        output = tmp_path / label
        result = subprocess.run(
            [
                "bash",
                str(source / "scripts/build-immutable-release.sh"),
                "--git-sha",
                sha,
                "--registry",
                REGISTRY,
                "--output-dir",
                str(output),
                *args,
            ],
            env=env | extra_env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, output

    return run, state


def test_first_publish_and_rerun_preserve_exact_artifact(release_cli):
    run, state = release_cli
    first, original = run("first")
    assert first.returncode == 0, first.stderr
    calls_before = (state / "calls").read_text()
    second, reused = run("second", GITHUB_RUN_ID="456")
    assert second.returncode == 0, second.stderr
    for path in original.iterdir():
        assert path.read_bytes() == (reused / path.name).read_bytes()
    calls_after = (state / "calls").read_text()[len(calls_before) :]
    assert '"buildx"' not in calls_after
    assert calls_before.count('"buildx"') == 4


@pytest.mark.parametrize("error", ["PERMISSION_DENIED: denied", "connection timed out"])
def test_lookup_errors_never_build(release_cli, error):
    run, state = release_cli
    result, _ = run("failure", LOOKUP_ERROR=error)
    assert result.returncode != 0
    assert all(
        json.loads(line)[0] != "docker" for line in (state / "calls").read_text().splitlines()
    )


def test_empty_successful_registry_response_is_rejected(release_cli):
    run, state = release_cli
    result, _ = run("empty", EMPTY_DIGEST="1")
    assert result.returncode != 0
    assert '"buildx"' not in (state / "calls").read_text()


def test_service_lookup_error_propagates_from_command_substitution(release_cli):
    run, state = release_cli
    result, _ = run(
        "denied", LOOKUP_ERROR="PERMISSION_DENIED: denied", LOOKUP_SERVICE="strayhub-api"
    )
    assert result.returncode != 0
    assert '"buildx"' not in (state / "calls").read_text()


def test_cache_v2_is_passed_to_each_service_build(release_cli):
    run, state = release_cli
    result, _ = run(
        "cached", ACTIONS_RESULTS_URL="https://cache.invalid", ACTIONS_RUNTIME_TOKEN="test"
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in (state / "calls").read_text().splitlines()]
    builds = [call for call in calls if call[1:3] == ["buildx", "build"]]
    for service, call in zip(("api", "worker", "web"), builds, strict=False):
        assert f"type=gha,scope=strayhub-{service},version=2" in call
        assert f"type=gha,mode=max,scope=strayhub-{service},version=2" in call


def test_reuse_only_missing_artifact_never_builds(release_cli):
    run, state = release_cli
    result, _ = run("missing", "--reuse-only")
    assert result.returncode != 0
    assert '"buildx"' not in (state / "calls").read_text()


def test_partial_publish_resumes_without_rebuilding_api(release_cli):
    run, state = release_cli
    failed, _ = run("failed", FAIL_BUILD="strayhub-worker")
    assert failed.returncode != 0
    before = (state / "calls").read_text()
    resumed, _ = run("resumed")
    assert resumed.returncode == 0, resumed.stderr
    calls = [json.loads(line) for line in (state / "calls").read_text()[len(before) :].splitlines()]
    builds = [call for call in calls if call[1:3] == ["buildx", "build"]]
    assert len(builds) == 3
    assert all("strayhub-api:" not in " ".join(call) for call in builds)


def test_corrupt_identity_is_rejected_without_rebuild(release_cli):
    run, state = release_cli
    first, _ = run("first")
    assert first.returncode == 0, first.stderr
    identity_path = state / "artifact/release-identity.json"
    identity = json.loads(identity_path.read_text())
    identity["manifest_sha256"] = "0" * 64
    identity_path.write_text(json.dumps(identity))
    before = (state / "calls").read_text()
    second, _ = run("corrupt")
    assert second.returncode != 0
    assert "manifest checksum mismatch" in second.stderr
    assert '"buildx"' not in (state / "calls").read_text()[len(before) :]
