"""Compatibility entry for explicit, local-only test-fixture cleanup."""

import argparse
import asyncio

from scripts.cleanup_legacy_demo_fixtures import cleanup


async def reset() -> int:
    result = await cleanup(apply=True)
    return result["delete_counts"].get("organizations", 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Reset requires --yes; preview with scripts.cleanup_legacy_demo_fixtures")
    print(f"已刪除 {asyncio.run(reset())} 個本機 fixture Organization")


if __name__ == "__main__":
    main()
