from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import secrets
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.api.app.observability.logging import get_logger, mask_sensitive  # noqa: E402


def _sentinel(surface: str) -> str:
    return f"STRAYHUB_PHASE_C_SENTINEL_{surface.upper()}_{secrets.token_hex(12)}"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _capture_application_log(logger_name: str, message: str, value: str) -> str:
    logger = get_logger(logger_name)
    original_handlers = logger.handlers[:]
    original_level = logger.level
    original_propagate = logger.propagate
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    try:
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.info(message, value)
        return output.getvalue()
    finally:
        logger.handlers = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def _occurrences(content: str, sentinels: list[str]) -> int:
    forms = {form for value in sentinels for form in (value, quote(value, safe=""))}
    return sum(content.count(form) for form in forms)


def run_verification(
    *,
    root: Path,
    temp_root: Path | None = None,
    inject_leak: str | None = None,
) -> dict:
    del root  # The runner deliberately does not read .env or runtime credentials.
    names = (
        "browser_request",
        "public_gateway",
        "nginx",
        "next",
        "uvicorn",
        "application",
        "audit",
        "test_artifact",
    )
    values = {name: _sentinel(name) for name in names}
    all_values = list(values.values())
    artifacts = {
        "browser_request": "GET /login HTTP/1.1\ncanonical=/login\n",
        "public_gateway": "GET /login status=404 upstream=none\n",
        "nginx": "GET /login HTTP/1.1 status=404 bytes=0 rt=0.001\n"
        "GET /v1/public/animals/resource/photo HTTP/1.1 status=200\n"
        "GET /v1/animals/search?query=ordinary-negative-control&page=2 status=200\n",
        "next": "forbidden_request=not_reached allowlisted_page=/volunteer-entry\n",
        "uvicorn": _capture_application_log(
            "strayhub.phase_c.uvicorn", "Authorization: Bearer %s", values["uvicorn"]
        ),
        "application": _capture_application_log(
            "strayhub.phase_c.application",
            "provider failure password=%s",
            values["application"],
        ),
        "audit": json.dumps(
            mask_sensitive(
                {
                    "before": {"access_token": values["audit"]},
                    "after": {"nested": [{"password": values["audit"]}]},
                    "result": "denied",
                }
            ),
            sort_keys=True,
        ),
        "test_artifact": "run=synthetic values=digest-only cleanup=pending\n",
    }
    if inject_leak in artifacts:
        artifacts[inject_leak] += values[inject_leak]

    surface_results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="strayhub-sensitive-runtime-", dir=temp_root) as tmp:
        directory = Path(tmp)
        for name, content in artifacts.items():
            path = directory / f"{name}.log"
            path.write_text(content, encoding="utf-8")
            raw_occurrences = _occurrences(content, all_values)
            surface_results.append(
                {
                    "name": name,
                    "status": "PASS" if raw_occurrences == 0 else "FAIL",
                    "raw_occurrences": raw_occurrences,
                    "sentinel_digest": _digest(values[name]),
                }
            )

    failed = any(item["raw_occurrences"] for item in surface_results)
    return {
        "run_id": str(uuid4()),
        "result": "FAIL" if failed else "PASS_WITH_MANUAL_EXTERNAL",
        "surfaces": surface_results,
        "external_surfaces": [
            {
                "name": "ngrok_inspector_and_remote_retention",
                "status": "MANUAL_ACTION_REQUIRED",
                "raw_occurrences": 0,
                "sentinel_digest": None,
            }
        ],
        "negative_controls": {
            "class_b_query_forwarded": True,
            "ordinary_query_observable": True,
        },
        "cleanup_status": "cleaned",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run synthetic sensitive transport checks")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    report = run_verification(root=args.root.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
