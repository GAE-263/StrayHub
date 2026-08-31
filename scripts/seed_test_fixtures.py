"""Explicit ORG-A/ORG-B/ORG-DISABLED test universe; never part of normal demo."""

from __future__ import annotations

from scripts.seed_local import seed
from scripts.test_database import require_fixture_database


def main() -> None:
    require_fixture_database()
    from scripts.seed_local import main

    main()


__all__ = ["seed"]

if __name__ == "__main__":
    main()
