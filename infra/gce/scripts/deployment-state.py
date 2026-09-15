#!/usr/bin/env python3
"""Durable deployment acknowledgements, never an automatic recovery decision.

Callers hold the common host flock throughout plan/checkpoint/finish and all runtime changes.
Unknown migration outcomes are deliberately not replayable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

STAGES = (
    "release_preparation",
    "secret_materialization",
    "image_pull",
    "preflight",
    "previous_pointer_read",
    "runtime_stop",
    "migration",
    "migration_head",
    "pointer_prepare",
    "pointer_switch",
    "unit_install",
    "runtime_start",
    "runtime_verification",
    "public_verification",
    "receipt_write",
    "receipt_activation",
    "complete",
)
PRE_MIGRATION = set(STAGES[:6])
RELEASE = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}")


def read(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate state key")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("state must be an object")
    return value


def atomic(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise ValueError("state file must not be a symlink")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def receipt_matches(receipt: dict, manifest: dict) -> bool:
    return receipt.get("verification") == "passed" and all(
        key in receipt and key in manifest and receipt[key] == manifest[key]
        for key in ("release_id", "git_sha", "images", "migration_revision")
    )


def plan(manifest_path: Path, state: Path, current: Path, resume: bool) -> tuple[str, str]:
    manifest = read(manifest_path)
    release = manifest["release_id"]
    if not RELEASE.fullmatch(release):
        raise ValueError("invalid release ID")
    identity = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    journal = state / f"{release}.checkpoint.json"
    active = state / "active-deployment.json"
    if journal.is_symlink() or active.is_symlink():
        raise ValueError("checkpoint must not be a symlink")
    if active.exists() and read(active).get("release_id") != release:
        raise ValueError("another deployment requires recovery before any new deployment")
    actual = current.resolve().name if current.is_symlink() else ""
    if actual and current.resolve() != current.parent / "releases" / actual:
        raise ValueError("current points outside canonical release root")
    if current.exists() and not current.is_symlink():
        raise ValueError("current must be a symlink")
    if not resume:
        if journal.exists() or actual == release:
            raise ValueError("existing deployment requires explicit resume")
        if actual:
            previous_manifest = read(current / "release-manifest.json")
            if (
                not RELEASE.fullmatch(actual)
                or not receipt_matches(read(state / "current.json"), previous_manifest)
                or previous_manifest["release_id"] != actual
            ):
                raise ValueError("previous pointer/receipt/manifest mismatch")
        data = {
            "schema_version": 1,
            "release_id": release,
            "manifest_sha256": identity,
            "previous_release_id": actual,
            "stage": "release_preparation",
        }
        # Active marker first: an interrupted initialization cannot admit another release.
        atomic(active, {"release_id": release})
        atomic(journal, data)
        return "prepare", actual
    data = read(journal)
    if (
        data.get("schema_version") != 1
        or data.get("release_id") != release
        or (data.get("manifest_sha256") != identity)
    ):
        raise ValueError("checkpoint artifact identity mismatch")
    previous = data["previous_release_id"]
    if previous and not RELEASE.fullmatch(previous):
        raise ValueError("invalid previous release")
    stage = data["stage"]
    if stage not in STAGES:
        raise ValueError("unknown checkpoint stage")
    if actual == release and stage in STAGES[9:]:
        return "verify", previous
    if actual == previous and stage in PRE_MIGRATION:
        if actual and not receipt_matches(
            read(state / "current.json"), read(current / "release-manifest.json")
        ):
            raise ValueError("previous receipt changed during interrupted deployment")
        return "prepare", previous
    raise ValueError("migration/pointer outcome requires manual investigation; resume refused")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "checkpoint", "status", "clear", "head"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--current-link", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stage", choices=STAGES)
    args = parser.parse_args()
    if args.command == "head":
        lines = sys.stdin.read().splitlines()
        heads = [
            line.strip()
            for line in lines
            if re.fullmatch(r"[A-Za-z0-9_.-]+ \(head\)", line.strip())
        ]
        if not args.revision or heads != [f"{args.revision} (head)"]:
            raise ValueError("live database must have exactly the expected migration head")
        return
    if not all((args.manifest, args.state_dir, args.current_link)):
        raise ValueError("manifest, state directory and current link required")
    manifest = read(args.manifest)
    release = manifest["release_id"]
    if not RELEASE.fullmatch(release):
        raise ValueError("invalid release ID")
    journal = args.state_dir / f"{release}.checkpoint.json"
    if args.command == "plan":
        mode, previous = plan(args.manifest, args.state_dir, args.current_link, args.resume)
        print(f"{mode} {previous or 'none'}")
    elif args.command == "status":
        # Read-only: checkpoint describes attempted action, not proof it completed.
        current = args.current_link.resolve().name if args.current_link.is_symlink() else None
        receipt = (
            read(args.state_dir / "current.json")
            if (args.state_dir / "current.json").exists()
            else {}
        )
        print(
            json.dumps(
                {
                    "checkpoint": read(journal) if journal.exists() else None,
                    "current_release": current,
                    "receipt_matches_target": receipt_matches(receipt, manifest),
                    "deployed_without_receipt": current == release
                    and not receipt_matches(receipt, manifest),
                }
            )
        )
    else:
        data = read(journal)
        if data["manifest_sha256"] != hashlib.sha256(args.manifest.read_bytes()).hexdigest():
            raise ValueError("checkpoint artifact mismatch")
        if args.command == "checkpoint":
            if args.stage is None:
                raise ValueError("stage required")
            data["stage"] = args.stage
            atomic(journal, data)
        else:
            if (
                data["stage"] != "complete"
                or not receipt_matches(read(args.state_dir / "current.json"), manifest)
                or args.current_link.resolve().name != release
            ):
                raise ValueError("cannot clear an incomplete deployment")
            active = args.state_dir / "active-deployment.json"
            if active.exists():
                if read(active).get("release_id") != release:
                    raise ValueError("active deployment mismatch")
                active.unlink()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"deployment state refused: {exc}") from None
