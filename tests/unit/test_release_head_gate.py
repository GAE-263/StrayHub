from __future__ import annotations

import json
import subprocess

import pytest
from scripts.release_head_gate import (
    RELEASE_ENDPOINT,
    ReleaseHeadError,
    read_current_release_head,
    validate_release_head_response,
)

SHA_A = "a" * 40
SHA_B = "b" * 40


def response(sha: str = SHA_A, *, object_type: str = "commit") -> bytes:
    return json.dumps(
        {"ref": "refs/heads/release", "object": {"sha": sha, "type": object_type}}
    ).encode()


def test_current_release_head_must_match_all_write_identities() -> None:
    assert validate_release_head_response(response(), SHA_A, SHA_A, SHA_A) == SHA_A
    with pytest.raises(ReleaseHeadError, match="does not match"):
        validate_release_head_response(response(SHA_B), SHA_A, SHA_A, SHA_A)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b'{"ref":"refs/heads/release","object":{"sha":"short","type":"commit"}}',
        b'{"ref":"refs/heads/release","object":{"sha":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","type":"commit"}}',
        response(object_type="tag"),
        response() + b"\n" + response(),
    ],
)
def test_release_head_readback_fails_closed(raw: bytes) -> None:
    with pytest.raises(ReleaseHeadError):
        validate_release_head_response(raw, SHA_A, SHA_A, SHA_A)


def test_observe_mode_records_superseded_release_after_deploy() -> None:
    assert (
        validate_release_head_response(response(SHA_B), SHA_A, SHA_A, SHA_A, allow_superseded=True)
        == SHA_B
    )


def test_authoritative_readback_uses_fixed_repository_and_stops_before_mutation() -> None:
    calls: list[list[str]] = []
    mutations: list[str] = []

    def stale_runner(command, **kwargs):
        calls.append(command)
        assert kwargs == {"capture_output": True, "check": False, "timeout": 15}
        return subprocess.CompletedProcess(command, 0, response(SHA_B), b"")

    with pytest.raises(ReleaseHeadError, match="does not match"):
        read_current_release_head(SHA_A, SHA_A, SHA_A, runner=stale_runner)
        mutations.append("external-write")
    assert calls == [["gh", "api", "--method", "GET", RELEASE_ENDPOINT]]
    assert mutations == []


@pytest.mark.parametrize(
    "completed",
    [
        subprocess.CompletedProcess([], 1, b"", b"unavailable"),
        subprocess.CompletedProcess([], 0, b"", b""),
        subprocess.CompletedProcess([], 0, response() + b"\n" + response(), b""),
    ],
)
def test_authoritative_readback_failure_is_fail_closed(completed) -> None:
    with pytest.raises(ReleaseHeadError):
        read_current_release_head(SHA_A, SHA_A, SHA_A, runner=lambda *args, **kwargs: completed)
