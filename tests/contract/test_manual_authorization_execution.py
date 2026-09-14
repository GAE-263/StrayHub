"""Execute manual authorization shell steps with isolated, offline Git/GitHub clients."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
BUNDLE = "b" * 64
TOKEN = "synthetic-offline-github-token"


def execute_step(tmp_path: Path, operation: str, **overrides: str) -> subprocess.CompletedProcess:
    yaml = __import__("yaml")
    filename = "line-rich-menu-publish.yml" if operation == "line" else "gce-release.yml"
    doc = yaml.load((ROOT / ".github/workflows" / filename).read_text(), Loader=yaml.BaseLoader)
    job = doc["jobs"]["publish" if operation == "line" else "authorize-manual-write"]
    checkout = next(s for s in job["steps"] if "actions/checkout" in s.get("uses", ""))
    assert checkout["with"]["persist-credentials"] == "false"
    step = next(s for s in job["steps"] if "manual_release_gate" in s.get("run", ""))
    ctx = {
        "github.actor": "yawan0203",
        "github.triggering_actor": "yawan0203",
        "github.run_attempt": "1",
        "github.token": TOKEN,
        "inputs.operation": operation,
        "inputs.git_sha": SHA,
        "inputs.confirmation": (
            f"PUBLISH LINE MENU {SHA}"
            if operation == "line"
            else f"DEPLOY PRODUCTION {SHA} {BUNDLE}"
            if operation == "deploy"
            else f"PUBLISH {SHA}"
        ),
        "inputs.release_bundle_sha256": BUNDLE if operation == "deploy" else "",
        "inputs.line_token_secret_version": "2",
    }
    ctx.update({k: v for k, v in overrides.items() if k in ctx})

    def render(text: str) -> str:
        for key, value in ctx.items():
            text = text.replace("${{ " + key + " }}", value)
        assert "${{" not in text
        return text

    bindir = tmp_path / "bin"
    bindir.mkdir()
    client = (
        f"#!{sys.executable}\n"
        + """
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['CALLS'], 'a') as f:
    f.write(name + ' ' + ' '.join(sys.argv[1:]) + '\\n')
if name == 'git':
    args = sys.argv[1:]
    if args == ['rev-parse', 'HEAD']:
        print(os.environ['CHECKOUT_SHA'])
    elif args[:2] == ['cat-file', '-t']:
        print('commit')
    elif args[:2] == ['merge-base', '--is-ancestor']:
        pass
    else:
        sys.stderr.write("fatal: could not read Username for 'https://github.com'\\n")
        sys.exit(128)
elif name == 'gh':
    endpoint = '/repos/GAE-263/StrayHub/git/ref/heads/release'
    assert sys.argv[1:] == ['api', '--method', 'GET', endpoint]
    assert os.environ.get('GH_TOKEN') == 'synthetic-offline-github-token'
    sys.stdout.write(os.environ['API_RESPONSE'])
    sys.exit(int(os.environ['API_STATUS']))
else:
    sys.exit('external mutation forbidden in authorization')
"""
    )
    for name in ("git", "gh", "gcloud", "docker", "ssh", "curl"):
        p = bindir / name
        p.write_text(client)
        p.chmod(0o700)
    (bindir / "python3").symlink_to(sys.executable)
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GITHUB_REPOSITORY": overrides.get("repository", "GAE-263/StrayHub"),
        "GITHUB_EVENT_NAME": overrides.get("event", "workflow_dispatch"),
        "GITHUB_REF": overrides.get("ref", "refs/heads/release"),
        "GITHUB_SHA": overrides.get("github_sha", SHA),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        "CHECKOUT_SHA": overrides.get("checkout_sha", SHA),
        "API_RESPONSE": overrides.get(
            "response",
            json.dumps({"ref": "refs/heads/release", "object": {"type": "commit", "sha": SHA}}),
        ),
        "API_STATUS": overrides.get("api_status", "0"),
        "CALLS": str(tmp_path / "calls"),
    }
    env.update({k: render(v) for k, v in step.get("env", {}).items()})
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", render(step["run"])],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert TOKEN not in result.stdout + result.stderr
    assert not any((tmp_path / p).exists() for p in (".gitconfig", ".git-credentials"))
    calls = (tmp_path / "calls").read_text()
    assert not any(
        line.split()[0] in {"gcloud", "docker", "ssh", "curl"} for line in calls.splitlines()
    )
    return result


@pytest.mark.parametrize("operation", ["publish", "deploy", "line"])
def test_manual_authorization_without_persisted_git_credentials(
    tmp_path: Path, operation: str
) -> None:
    result = execute_step(tmp_path, operation)
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "calls").read_text()
    assert "gh api --method GET /repos/GAE-263/StrayHub/git/ref/heads/release" in calls
    assert "git fetch" not in calls


@pytest.mark.parametrize("operation", ["publish", "deploy", "line"])
@pytest.mark.parametrize(
    "overrides",
    [
        {
            "response": json.dumps(
                {"ref": "refs/heads/release", "object": {"type": "commit", "sha": "c" * 40}}
            )
        },
        {
            "response": '{"ref":"refs/heads/release","object":{"type":"commit","sha":"'
            + SHA
            + '","sha":"'
            + SHA
            + '"}}'
        },
        {"response": ""},
        {"response": "{}"},
        {"response": "not-json"},
        {"api_status": "1"},
        {"github.actor": "someone-else"},
        {"github.triggering_actor": "someone-else"},
        {"github.run_attempt": "2"},
        {"inputs.confirmation": "wrong"},
        {"github_sha": "c" * 40},
        {"checkout_sha": "c" * 40},
        {"repository": "someone/else"},
        {"event": "push"},
        {"event": "pull_request"},
        {"ref": "refs/heads/main"},
    ],
)
def test_manual_authorization_refuses_invalid_context(
    tmp_path: Path, operation: str, overrides: dict[str, str]
) -> None:
    result = execute_step(tmp_path, operation, **overrides)
    assert result.returncode != 0
    summary = tmp_path / "summary"
    assert not summary.exists() or "Authorized" not in summary.read_text()
