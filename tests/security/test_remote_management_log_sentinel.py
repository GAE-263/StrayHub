from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_sensitive_transport_runtime import run_verification


def test_phase_e_cross_layer_sentinel_and_negative_controls(tmp_path: Path) -> None:
    report = run_verification(root=Path.cwd(), temp_root=tmp_path)
    rendered = json.dumps(report, sort_keys=True)

    assert report["result"] == "PASS_WITH_MANUAL_EXTERNAL"
    assert all(surface["raw_occurrences"] == 0 for surface in report["surfaces"])
    assert report["negative_controls"]["ordinary_query_observable"] is True
    assert report["negative_controls"]["class_b_query_forwarded"] is True
    assert "STRAYHUB_PHASE_E_SENTINEL_" not in rendered
