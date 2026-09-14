"""Fail-closed readback of the authoritative release branch head."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

REPOSITORY = "GAE-263/StrayHub"
RELEASE_REF = "refs/heads/release"
RELEASE_ENDPOINT = f"/repos/{REPOSITORY}/git/ref/heads/release"
SHA_RE = re.compile(r"[0-9a-f]{40}")


class ReleaseHeadError(RuntimeError):
    """The authoritative release head could not be proven."""


Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseHeadError("duplicate_json_key")
        result[key] = value
    return result


def validate_release_head_response(
    raw: bytes,
    requested_sha: str,
    github_sha: str,
    checkout_sha: str,
    *,
    allow_superseded: bool = False,
) -> str:
    identities = (requested_sha, github_sha, checkout_sha)
    if any(not SHA_RE.fullmatch(value) for value in identities) or len(set(identities)) != 1:
        raise ReleaseHeadError("requested, workflow, and checkout SHAs do not match")
    try:
        document = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseHeadError("authoritative release readback is invalid") from exc
    if not isinstance(document, dict) or document.get("ref") != RELEASE_REF:
        raise ReleaseHeadError("authoritative release ref is invalid")
    target = document.get("object")
    if not isinstance(target, dict) or target.get("type") != "commit":
        raise ReleaseHeadError("authoritative release target is not a commit")
    current_sha = target.get("sha")
    if not isinstance(current_sha, str) or not SHA_RE.fullmatch(current_sha):
        raise ReleaseHeadError("authoritative release SHA is invalid")
    if not allow_superseded and current_sha != requested_sha:
        raise ReleaseHeadError("authoritative release HEAD does not match requested SHA")
    return current_sha


def read_current_release_head(
    requested_sha: str,
    github_sha: str,
    checkout_sha: str,
    *,
    allow_superseded: bool = False,
    runner: Runner = subprocess.run,
) -> str:
    try:
        completed = runner(
            ["gh", "api", "--method", "GET", RELEASE_ENDPOINT],
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseHeadError("authoritative release readback failed") from exc
    if completed.returncode != 0:
        raise ReleaseHeadError("authoritative release readback failed")
    return validate_release_head_response(
        completed.stdout,
        requested_sha,
        github_sha,
        checkout_sha,
        allow_superseded=allow_superseded,
    )


def _write_output(path: Path, current_sha: str, requested_sha: str) -> None:
    superseded = "true" if current_sha != requested_sha else "false"
    path.write_text(
        f"current_release_sha={current_sha}\nrelease_superseded_after_deploy={superseded}\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requested-sha", required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--allow-superseded", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        current_sha = read_current_release_head(
            args.requested_sha,
            args.github_sha,
            args.checkout_sha,
            allow_superseded=args.allow_superseded,
        )
    except ReleaseHeadError as exc:
        parser.error(str(exc))
    if args.github_output:
        _write_output(args.github_output, current_sha, args.requested_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
