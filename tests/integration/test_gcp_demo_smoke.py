import os
from pathlib import Path


def test_gcp_demo_smoke_requires_explicit_deployed_environment() -> None:
    evidence = Path("infra/gcp-demo/deployment-evidence.md").read_text(encoding="utf-8")
    if os.getenv("RUN_GCP_DEMO_SMOKE") != "1":
        return
    assert "T243 Cloud SQL／GCS／LINE／QR／A-B／AI smoke" in evidence
    assert "待填" not in evidence
