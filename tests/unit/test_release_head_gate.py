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
INVALID_SHAS: tuple[object, ...] = (None, 1, [], {}, " " + SHA_A, SHA_A + "\n" + SHA_B)


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


@pytest.mark.parametrize("allow_superseded", [False, True])
@pytest.mark.parametrize(
    "raw",
    [
        # Both orders must reject, including when last-key-wins would authorize A.
        (
            '{"ref":"refs/heads/release","object":{"type":"commit","sha":"'
            + first
            + '"},"object":{"type":"commit","sha":"'
            + second
            + '"}}'
        ).encode()
        for first, second in ((SHA_A, SHA_B), (SHA_B, SHA_A))
    ]
    + [
        (
            '{"ref":"refs/heads/release","object":{"type":"commit","sha":"'
            + first
            + '","sha":"'
            + second
            + '"}}'
        ).encode()
        for first, second in ((SHA_A, SHA_B), (SHA_B, SHA_A))
    ]
    + [
        response()[:-1]
        + b',"metadata":{"items":[{"private-key-marker":1,"private-key-marker":2}]}}',
        response()[:-1] + b',"metadata":{"name":1,"na\\u006de":1}}',
    ],
)
def test_duplicate_keys_rejected_recursively(raw: bytes, allow_superseded: bool) -> None:
    with pytest.raises(ReleaseHeadError) as caught:
        validate_release_head_response(raw, SHA_A, SHA_A, SHA_A, allow_superseded=allow_superseded)
    assert str(caught.value) == "duplicate_json_key"


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"[]",
        b"null",
        b'"text"',
        b'{"ref":"refs/heads/release"}',
        b'{"ref":"refs/heads/release","object":{"type":"commit"}}',
        b'{"ref":"refs/heads/other","object":{}}',
        response() + b"garbage",
    ]
    + [
        json.dumps({"ref": "refs/heads/release", "object": {"type": "commit", "sha": sha}}).encode()
        for sha in INVALID_SHAS
    ],
)
def test_invalid_response_schema_and_trailing_data(raw: bytes) -> None:
    with pytest.raises(ReleaseHeadError):
        validate_release_head_response(raw, SHA_A, SHA_A, SHA_A)


@pytest.mark.parametrize("operation", ["publish", "deploy", "line"])
def test_duplicate_response_stops_before_credentials_and_writes(operation: str) -> None:
    raw = response()[:-1] + b',"metadata":{"key":1,"key":2}}'
    counters = dict.fromkeys(
        ("WIF", "Secret Manager", "Registry push", "SSH/IAP", "LINE write", "GCS write"), 0
    )
    completed = subprocess.CompletedProcess([], 0, raw, b"")
    with pytest.raises(ReleaseHeadError, match="^duplicate_json_key$"):
        read_current_release_head(SHA_A, SHA_A, SHA_A, runner=lambda *args, **kwargs: completed)
        counters["WIF"] += 1
        targets = {
            "publish": ("Registry push",),
            "deploy": ("SSH/IAP",),
            "line": ("Secret Manager", "LINE write", "GCS write"),
        }
        for target in targets[operation]:
            counters[target] += 1
    assert all(count == 0 for count in counters.values())
