from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.verify_sensitive_transport_runtime import run_verification

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/verify_sensitive_transport_runtime.py"


def test_safe_runtime_report_contains_only_digests_and_cleans_artifacts(tmp_path: Path) -> None:
    report = run_verification(root=ROOT, temp_root=tmp_path)
    rendered = json.dumps(report, sort_keys=True)

    assert report["result"] == "PASS_WITH_MANUAL_EXTERNAL"
    assert report["cleanup_status"] == "cleaned"
    assert all(item["raw_occurrences"] == 0 for item in report["surfaces"])
    assert report["negative_controls"] == {
        "class_b_query_forwarded": True,
        "ordinary_query_observable": True,
    }
    assert "STRAYHUB_PHASE_C_SENTINEL_" not in rendered
    assert list(tmp_path.iterdir()) == []


def test_injected_leak_fails_without_echoing_the_sentinel(tmp_path: Path) -> None:
    report = run_verification(root=ROOT, temp_root=tmp_path, inject_leak="application")
    rendered = json.dumps(report, sort_keys=True)

    assert report["result"] == "FAIL"
    application = next(item for item in report["surfaces"] if item["name"] == "application")
    assert application["raw_occurrences"] == 1
    assert "STRAYHUB_PHASE_C_SENTINEL_" not in rendered
    assert list(tmp_path.iterdir()) == []


def test_runtime_cli_output_never_contains_raw_sentinel() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--root", str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "STRAYHUB_PHASE_C_SENTINEL_" not in result.stdout
    report = json.loads(result.stdout)
    assert report["cleanup_status"] == "cleaned"
