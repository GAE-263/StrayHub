"""CI evidence must be exact, complete and fresh before release credentials."""

import subprocess
from copy import deepcopy

import pytest
from scripts import main_ci_gate as gate

SHA = "a" * 40


@pytest.fixture
def evidence(monkeypatch):
    workflow = {"id": 17, "path": gate.WORKFLOW}
    run = dict(
        id=81,
        run_attempt=1,
        head_sha=SHA,
        head_branch="main",
        event="push",
        path=gate.WORKFLOW,
        status="completed",
        conclusion="success",
        workflow_id=17,
        repository={"full_name": gate.REPOSITORY},
        head_repository={"full_name": gate.REPOSITORY},
    )
    jobs = {
        "total_count": 5,
        "jobs": [
            dict(
                name=n,
                run_id=81,
                run_attempt=1,
                head_sha=SHA,
                status="completed",
                conclusion="success",
            )
            for n in sorted(gate.CHECKS)
        ],
    }
    responses = [workflow, {"workflow_runs": [run]}, jobs, deepcopy(run)]
    calls = []

    def gh(endpoint):
        calls.append(endpoint)
        return responses[len(calls) - 1]

    monkeypatch.setattr(gate, "gh", gh)
    return responses, calls


def test_success_uses_only_readback_and_exact_attempt(evidence):
    _, calls = evidence
    assert gate.verify(SHA) == 81
    assert "head_sha=" + SHA in calls[1]
    assert "attempts/1/jobs" in calls[2]


@pytest.mark.parametrize(
    "key,value",
    [
        ("head_sha", "b" * 40),
        ("event", "pull_request"),
        ("head_branch", "release"),
        ("path", ".github/workflows/other.yml"),
        ("workflow_id", 18),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("conclusion", "cancelled"),
        ("head_repository", {"full_name": "someone/fork"}),
        ("run_attempt", 0),
    ],
)
def test_untrusted_or_unsuccessful_run_refused(evidence, key, value):
    responses, _ = evidence
    responses[1]["workflow_runs"][0][key] = value
    with pytest.raises(ValueError):
        gate.verify(SHA)


@pytest.mark.parametrize(
    "key,value",
    [
        ("conclusion", "skipped"),
        ("conclusion", "failure"),
        ("status", "queued"),
        ("run_id", 82),
        ("run_attempt", 2),
        ("head_sha", "b" * 40),
        ("name", "other"),
    ],
)
def test_job_mismatch_refused(evidence, key, value):
    responses, _ = evidence
    responses[2]["jobs"][0][key] = value
    with pytest.raises(ValueError):
        gate.verify(SHA)


def test_missing_job_and_rerun_race_refused(evidence):
    responses, _ = evidence
    responses[2]["jobs"].pop()
    with pytest.raises(ValueError):
        gate.verify(SHA)


def test_rerun_race_refused(evidence):
    responses, _ = evidence
    responses[3]["run_attempt"] = 2
    with pytest.raises(ValueError):
        gate.verify(SHA)


def test_no_main_evidence_refused(evidence):
    responses, _ = evidence
    responses[1]["workflow_runs"] = []
    with pytest.raises(ValueError):
        gate.verify(SHA)


def test_invalid_sha_does_not_call_github(evidence):
    _, calls = evidence
    with pytest.raises(ValueError):
        gate.verify("main")
    assert not calls


def test_transport_failure_never_echoes_raw_credentials(monkeypatch, capsys):
    def failed(_):
        raise subprocess.CalledProcessError(1, ["gh"], stderr=b"synthetic-private-token")

    monkeypatch.setattr(gate, "gh", failed)
    monkeypatch.setattr("sys.argv", ["main_ci_gate", "--git-sha", SHA])
    with pytest.raises(SystemExit) as exc:
        gate.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "synthetic-private-token" not in captured.out + captured.err
    assert "refusing credentials" in captured.err
