"""Explicit ORG-A/ORG-B/ORG-DISABLED test universe; never part of normal demo."""

from __future__ import annotations

from scripts.test_database import require_test_database


async def seed(*args, **kwargs):
    require_test_database()
    from scripts.seed_local import seed as seed_local

    return await seed_local(*args, **kwargs)


def main() -> None:
    require_test_database()
    from scripts.seed_local import main as seed_local_main

    seed_local_main()


__all__ = ["seed"]

if __name__ == "__main__":
    main()
