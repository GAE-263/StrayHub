"""Execute the full deploy script with a deny-by-default, temporary-only toolchain."""

from __future__ import annotations

import fcntl
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NEW = "20260910T000000Z-" + "a" * 12
OLD = "20260909T000000Z-" + "b" * 12

# No subprocesses in the stub: even an unexpected executable cannot reach Docker,
# systemd or the cloud. The script's argument parsing/control flow/trap is real.
STUB = r"""
import fcntl, json, os, subprocess, sys
from pathlib import Path
root = Path(os.environ['TEST_ROOT'])
args = sys.argv[1:]
name = Path(sys.argv[0]).name
scenario = os.environ['SCENARIO']
new = os.environ['NEW_RELEASE']
def path(value):
    result = Path(value)
    assert result.is_absolute() and result.is_relative_to(root), value
    return result
def event(value):
    with (root / 'trace').open('a') as out:
        out.write(value + '\n')
def fail(point, code):
    if scenario == point:
        event('fail:' + point)
        sys.exit(code)
def option(key):
    return args[args.index(key) + 1]
if name == 'dirname':
    print(path(args[0]).parent)
elif name == 'readlink':
    print(path(args[-1]).resolve())
elif name == 'install':
    for value in args[args.index('0755') + 1:]:
        path(value).mkdir(parents=True, exist_ok=True)
elif name == 'flock':
    fcntl.flock(int(args[-1]), fcntl.LOCK_EX | fcntl.LOCK_NB)
elif name == 'cmp':
    sys.exit(0 if path(args[-2]).read_bytes() == path(args[-1]).read_bytes() else 1)
elif name == 'python3':
    assert path(args[0]).name == 'deployment-state.py'
    sys.exit(subprocess.call([sys.executable, *args]))
elif name in ('chown', 'chmod'):
    path(args[-1])
elif name == 'systemctl':
    assert args[0] in ('daemon-reload', 'stop', 'start', 'reset-failed', 'restart')
    event('systemctl:' + args[0])
    if args[0] == 'restart':
        fail('start', 45)
elif name == 'docker':
    if 'pull' in args:
        event('pull')
    elif args[-1] == 'migration':
        event('migration')
        # A failed migration may already have changed state. Never undo it here.
        (root / 'migration-evidence').write_text('possibly changed')
        fail('migration', 42)
    elif args[-1] == 'current':
        event('head')
        fail('head-command', 43)
        print('wrong-head' if scenario == 'head-mismatch' else 'synthetic_head (head)')
    else:
        raise AssertionError('unexpected docker operation')
elif name == 'release-manifest.py':
    if args[0] == 'validate-artifact':
        event('validate')
    elif args[0] == 'show-field':
        print(new if option('--field') == 'release_id' else 'synthetic_head')
    elif args[0] == 'extract-artifact':
        event('extract')
        dest = path(option('--destination'))
        scripts = dest / 'infra/gce/scripts'
        scripts.mkdir(parents=True)
        (dest / 'infra/gce/docker-compose.production.yml').write_text('synthetic')
        (dest / 'image-digests.env').write_text('synthetic')
        (dest / 'release-manifest.json').write_text(json.dumps({'git_sha': 'a'*40,
            'release_id': new, 'images': {}, 'migration_revision': 'synthetic_head'}))
        for script in ('fetch-secrets.sh', 'production-preflight.sh',
                       'install-systemd-units.sh', 'verify-systemd-runtime.sh',
                       'release-manifest.py'):
            (scripts / script).symlink_to(root / 'bin' / script)
    elif args[0] == 'write-receipt':
        event('receipt')
        manifest = json.loads(path(option('--manifest')).read_text())
        manifest['previous_release_id'] = option('--previous-release') or None
        manifest['verification'] = 'passed'
        path(option('--output')).write_text(json.dumps(manifest))
        fail('receipt-after', 49)
    elif args[0] == 'validate-release-dir':
        path(option('--release-dir'))
    elif args[0] == 'validate-receipt':
        r = json.loads(path(option('--receipt')).read_text())
        assert r['release_id'] == new and r['verification'] == 'passed'
    elif args[0] == 'validate-predecessor':
        pass  # Binding semantics are covered using the real manifest validator separately.
    else:
        raise AssertionError('unexpected manifest command')
elif name == 'fetch-secrets.sh':
    event('materialize')
elif name == 'production-preflight.sh':
    event('preflight')
    fail('preflight', 41)
elif name == 'install-systemd-units.sh':
    event('units')
elif name == 'verify-systemd-runtime.sh':
    event('verify')
    fail('verification', 46)
elif name == 'ln':
    source, destination = path(args[-2]), path(args[-1])
    event('receipt-link' if destination.name == '.current.json.tmp' else 'pointer-prepare')
    if destination.name.startswith('.current-'):
        fail('pointer-prepare', 44)
    destination.symlink_to(source)
elif name == 'mv':
    source, destination = path(args[-2]), path(args[-1])
    event('receipt-activate' if destination.name == 'current.json' else 'pointer-switch')
    if destination.name == 'current':
        fail('pointer-before', 47)
    if destination.name == 'current.json':
        fail('receipt-activate', 50)
    os.replace(source, destination)
    if destination.name == 'current':
        # Model an ambiguous failure acknowledgement AFTER atomic replacement.
        fail('pointer-after', 48)
elif name == 'grep':
    sys.exit(0 if args[-1] in sys.stdin.read() else 1)
elif name == 'awk':
    path(args[-1])
    print('strayhub.enadv.quest')
elif name == 'curl':
    event('public')
elif name == 'date':
    print('2026-09-10T00:00:00Z')
else:
    raise AssertionError('unapproved stub operation: ' + name)
"""


def deploy(tmp_path: Path, scenario: str, *, broken_diagnostic: bool = False):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    commands = (
        "dirname readlink install chown chmod systemctl docker release-manifest.py "
        "fetch-secrets.sh production-preflight.sh install-systemd-units.sh "
        "verify-systemd-runtime.sh ln mv grep awk curl date python3 flock cmp"
    ).split()
    for name in commands:
        stub = bin_dir / name
        stub.write_text(f"#!{sys.executable}\n" + STUB)
        stub.chmod(0o755)
    script = (ROOT / "infra/gce/scripts/deploy-release.sh").read_text()
    # Redirect only filesystem roots and the privilege prerequisite, never the
    # deployment statements, EXIT trap, status handling or failure branches.
    for prefix in ("/opt/strayhub", "/etc/strayhub", "/var/lib/strayhub"):
        script = script.replace(prefix, str(tmp_path / prefix.lstrip("/")))
    assert "${EUID:-$(id -u)}" in script
    script = script.replace("${EUID:-$(id -u)}", "0")
    assert not any(f'"{prefix}' in script for prefix in ("/opt/", "/etc/", "/var/lib/"))
    executable = bin_dir / "deploy-release.sh"
    executable.write_text(script)
    (bin_dir / "deployment-state.py").write_text(
        (ROOT / "infra/gce/scripts/deployment-state.py").read_text()
    )
    releases = tmp_path / "opt/strayhub/releases"
    old = releases / OLD
    old.mkdir(parents=True)
    (old / "keep").write_text("old release evidence")
    old_manifest = {
        "release_id": OLD,
        "git_sha": "b" * 40,
        "images": {},
        "migration_revision": "synthetic_head",
    }
    (old / "release-manifest.json").write_text(json.dumps(old_manifest))
    (releases.parent / "current").symlink_to(old)
    config = tmp_path / "etc/strayhub/production.env"
    config.parent.mkdir(parents=True)
    config.write_text("E4_CANONICAL_HOSTNAME=strayhub.enadv.quest\n")
    secrets = tmp_path / "var/lib/strayhub/secrets"
    generation = secrets / "synthetic-generation"
    generation.mkdir(parents=True)
    (secrets / "current").symlink_to(generation)
    for name in ("runtime.env", "jwt-private.pem", "jwt-public.pem"):
        (generation / name).write_text("synthetic-not-a-credential")
    state = tmp_path / "var/lib/strayhub/releases"
    state.mkdir()
    old_receipt = json.dumps(old_manifest | {"verification": "passed"})
    (state / f"{OLD}.json").write_text(old_receipt)
    (state / "current.json").symlink_to(state / f"{OLD}.json")
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "release-manifest.json").write_text(
        json.dumps(
            {
                "git_sha": "a" * 40,
                "release_id": NEW,
                "images": {},
                "migration_revision": "synthetic_head",
            }
        )
    )
    (artifact / "keep").write_text("diagnostic evidence")
    env = {
        "PATH": str(bin_dir),
        "TEST_ROOT": str(tmp_path),
        "SCENARIO": scenario,
        "NEW_RELEASE": NEW,
    }
    if broken_diagnostic:
        bash_env = tmp_path / "bash-env"
        bash_env.write_text(
            'printf() { if [[ "$*" == *"[GCE release] deployment"* ]]; then '
            'builtin printf "diagnostic-failed\\n" >> "$TEST_ROOT/trace"; return 87; fi; '
            'builtin printf "$@"; }\n'
        )
        env["BASH_ENV"] = str(bash_env)
    # An inherited outer advisory FD verifies that even
    # error/diagnostic paths terminate and release an outer caller's OS lock.
    runner = (
        "import fcntl,os,sys; fd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600); "
        "fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); os.set_inheritable(fd,True); "
        "os.execve('/bin/bash',['/bin/bash']+sys.argv[2:],os.environ)"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            runner,
            str(tmp_path / "test.lock"),
            str(executable),
            "--artifact-dir",
            str(artifact),
            "--deployment-role",
            "synthetic tester",
            "--confirm-production",
            "DEPLOY_STRAYHUB_PRODUCTION",
        ],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    with (tmp_path / "test.lock").open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert (old / "keep").read_text() == "old release evidence"
    assert (state / f"{OLD}.json").read_text() == old_receipt
    assert (artifact / "keep").read_text() == "diagnostic evidence"
    return result, (tmp_path / "trace").read_text().splitlines(), releases, state


@pytest.mark.parametrize(
    "scenario,code,stage,switched,restarts",
    [
        ("preflight", 41, "preflight", False, 0),
        ("migration", 42, "migration", False, 0),
        ("head-command", 43, "migration_head", False, 0),
        ("head-mismatch", 1, "migration_head", False, 0),
        ("pointer-prepare", 44, "pointer_prepare", False, 0),
        ("pointer-before", 47, "pointer_switch", False, 0),
        ("pointer-after", 48, "pointer_switch", True, 0),
        ("start", 45, "runtime_start", True, 1),
        ("verification", 46, "runtime_verification", True, 1),
    ],
)
def test_deployment_failure_stops_without_automatic_recovery(
    tmp_path: Path,
    scenario: str,
    code: int,
    stage: str,
    switched: bool,
    restarts: int,
) -> None:
    result, calls, releases, state = deploy(tmp_path, scenario)
    assert result.returncode == code, result.stderr
    assert "systemctl:start" not in calls, calls
    assert calls.count("systemctl:restart") == restarts
    assert (releases.parent / "current").resolve() == releases / (NEW if switched else OLD)
    assert "receipt" not in calls
    assert not (state / f"{NEW}.json").exists()
    assert (state / "current.json").resolve() == state / f"{OLD}.json"
    if scenario == "preflight":
        assert "systemctl:stop" not in calls and "migration" not in calls
    else:
        assert calls.count("systemctl:stop") == 1
        assert (tmp_path / "migration-evidence").read_text() == "possibly changed"
    if scenario == "pointer-before":
        assert (releases.parent / f".current-{NEW}").is_symlink()
    if scenario == "pointer-after":
        assert not (releases.parent / f".current-{NEW}").is_symlink()
    assert f"stage={stage}" in result.stderr
    completed = {
        "preflight": "image_pull",
        "migration": "runtime_stop",
        "head-command": "migration",
        "head-mismatch": "migration",
        "pointer-prepare": "migration_head",
        "pointer-before": "pointer_prepare",
        "pointer-after": "pointer_prepare",
        "start": "unit_install",
        "verification": "runtime_start",
    }
    assert f"last_completed={completed[scenario]}" in result.stderr
    assert "state requires read-only verification" in result.stderr
    assert "[GCE release] PASS" not in result.stdout
    assert "synthetic-not-a-credential" not in result.stdout + result.stderr


def test_diagnostic_failure_cannot_replace_original_exit_status(tmp_path: Path) -> None:
    result, calls, _, _ = deploy(tmp_path, "migration", broken_diagnostic=True)
    assert result.returncode == 42
    assert calls.count("diagnostic-failed") == 1
    assert "systemctl:start" not in calls and "systemctl:restart" not in calls
    assert "receipt" not in calls


@pytest.mark.parametrize("scenario,code", [("receipt-after", 49), ("receipt-activate", 50)])
def test_partial_receipt_is_preserved_without_false_absence_claim(
    tmp_path: Path,
    scenario: str,
    code: int,
) -> None:
    result, calls, releases, state = deploy(tmp_path, scenario)
    assert result.returncode == code
    assert (state / f"{NEW}.json").is_file()
    assert (state / "current.json").resolve() == state / f"{OLD}.json"
    assert (releases.parent / "current").resolve() == releases / NEW
    assert "systemctl:start" not in calls
    assert calls.count("systemctl:restart") == 1  # Normal start BEFORE receipt failure.
    assert "no success receipt was written" not in result.stderr
    assert "state requires read-only verification" in result.stderr
    assert "[GCE release] PASS" not in result.stdout


def test_success_retains_sequence_and_exact_receipt_identity(tmp_path: Path) -> None:
    result, calls, releases, state = deploy(tmp_path, "success")
    assert result.returncode == 0, result.stderr
    assert calls == [
        "validate",
        "extract",
        "systemctl:daemon-reload",
        "materialize",
        "pull",
        "preflight",
        "systemctl:stop",
        "migration",
        "head",
        "pointer-prepare",
        "pointer-switch",
        "units",
        "systemctl:reset-failed",
        "systemctl:restart",
        "verify",
        "public",
        "public",
        "receipt",
        "receipt-link",
        "receipt-activate",
    ]
    assert (releases.parent / "current").resolve() == releases / NEW
    receipt = json.loads((state / "current.json").read_text())
    assert receipt == {
        "git_sha": "a" * 40,
        "release_id": NEW,
        "previous_release_id": OLD,
        "verification": "passed",
        "images": {},
        "migration_revision": "synthetic_head",
    }
    assert "[GCE release] PASS" in result.stdout


@pytest.mark.parametrize(
    "scenario",
    [
        "preflight",
        "receipt-after",
        "receipt-activate",
        "success",
        "migration",
        "head-command",
        "pointer-before",
    ],
)
def test_full_script_resume_does_not_replay_uncertain_migration(tmp_path: Path, scenario: str):
    _, _, _, state = deploy(tmp_path, scenario)
    before = (tmp_path / "trace").read_text()
    result = subprocess.run(
        [
            "/bin/bash",
            str(tmp_path / "bin/deploy-release.sh"),
            "--artifact-dir",
            str(tmp_path / "artifact"),
            "--deployment-role",
            "synthetic tester",
            "--confirm-production",
            "DEPLOY_STRAYHUB_PRODUCTION",
            "--resume",
        ],
        env={
            "PATH": str(tmp_path / "bin"),
            "TEST_ROOT": str(tmp_path),
            "SCENARIO": "success",
            "NEW_RELEASE": NEW,
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    calls = (tmp_path / "trace").read_text()[len(before) :].splitlines()
    if scenario in {"migration", "head-command", "pointer-before"}:
        assert result.returncode != 0
        assert "manual investigation" in result.stderr
        assert calls == ["validate"]
    else:
        assert result.returncode == 0, result.stderr
        assert not (state / "active-deployment.json").exists()
        if scenario != "preflight":
            assert "migration" not in calls
            assert not any(call.startswith("systemctl:") for call in calls)
            assert "materialize" not in calls and "pull" not in calls
            assert "receipt" not in calls  # Reuse and validate the already-created receipt.
        else:
            assert calls.count("migration") == 1
        assert json.loads((state / f"{NEW}.checkpoint.json").read_text())["stage"] == "complete"


def test_real_host_lock_refuses_second_resume_without_side_effects(tmp_path: Path):
    _, _, _, state = deploy(tmp_path, "preflight")
    before = (tmp_path / "trace").read_bytes()
    with (state / ".operation.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(
            [
                "/bin/bash",
                str(tmp_path / "bin/deploy-release.sh"),
                "--artifact-dir",
                str(tmp_path / "artifact"),
                "--deployment-role",
                "synthetic tester",
                "--confirm-production",
                "DEPLOY_STRAYHUB_PRODUCTION",
                "--resume",
            ],
            env={
                "PATH": str(tmp_path / "bin"),
                "TEST_ROOT": str(tmp_path),
                "SCENARIO": "success",
                "NEW_RELEASE": NEW,
            },
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=20,
        )
    assert result.returncode != 0
    assert "holds the host lock" in result.stderr
    assert (tmp_path / "trace").read_bytes() == before
