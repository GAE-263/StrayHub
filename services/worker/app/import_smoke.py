"""Offline, fresh-process task-loader preflight for the Worker image."""

from __future__ import annotations

import sys
import traceback


def main() -> int:
    # Import must not contact a broker, database, metadata server, or external API.
    # This hook lasts for this short-lived process only.
    def deny_network(event: str, args: object) -> None:
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise RuntimeError("network access during task registry import")

    sys.addaudithook(deny_network)
    try:
        from services.api.app.config.settings import get_worker_settings

        get_worker_settings()
        from services.api.app.infrastructure.celery_app import celery_app

        celery_app.loader.import_default_modules()
        if "services.api.app.persistence.database.engine" in sys.modules:
            raise RuntimeError("task registry imported the API database engine")
    except Exception as exc:
        # Exception messages/source lines may contain credentials. Emit only type
        # and code locations, never settings, values, or local variables.
        print(f"[Worker task import] FAIL: {type(exc).__name__}", file=sys.stderr)
        for frame in traceback.extract_tb(exc.__traceback__):
            print(f"  {frame.filename}:{frame.lineno} in {frame.name}", file=sys.stderr)
        return 1
    print("[Worker task import] PASS: full default task registry loaded offline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
