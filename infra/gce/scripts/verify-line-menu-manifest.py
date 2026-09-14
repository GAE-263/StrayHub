#!/usr/bin/env python3
"""Validate the authoritative publication manifest without contacting LINE."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.line_menu_manifest import MenuManifestError, load_publication_manifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--expected-bot", required=True)
    args = parser.parse_args()
    try:
        result = load_publication_manifest(
            args.manifest,
            expected_git_sha=args.expected_git_sha,
            expected_bot_basic_id=args.expected_bot,
        )
    except MenuManifestError as exc:
        parser.exit(1, f"LINE menu manifest invalid: {exc}\n")
    print(
        json.dumps(
            {
                "schema_version": 1,
                "git_sha": result.git_sha,
                "bot_basic_id": result.bot_basic_id,
                "manifest_sha256": result.manifest_sha256,
                "menus": result.menus,
                "validation": "passed",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
