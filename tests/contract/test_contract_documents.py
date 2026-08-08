from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_contract_documents_reference_the_same_local_mvp_boundaries() -> None:
    openapi = yaml.safe_load(
        (ROOT / "specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = openapi["paths"]
    assert "/v1/animals/{animalId}/timeline" in paths
    assert "/v1/line/webhook" in paths
    assert "/v1/care-reports" in paths
    generated = (ROOT / "packages/contracts/src/openapi.ts").read_text()
    assert "animals/{animalId}/timeline" in generated
    assert "line/webhook" in generated

    for relative in (
        "specs/001-volunteer-care-report/data-model.md",
        "specs/001-volunteer-care-report/quickstart.md",
        "specs/001-volunteer-care-report/plan.md",
        "specs/001-volunteer-care-report/contracts/generated-types.md",
        "specs/001-volunteer-care-report/contracts/object-storage.md",
        "specs/001-volunteer-care-report/contracts/async-ai.md",
        "services/api/app/application/ports/line_messaging.py",
        "services/api/app/infrastructure/storage/ports.py",
        "services/api/app/persistence/models/ai_job.py",
    ):
        assert (ROOT / relative).exists(), relative


def test_quickstart_and_local_commands_use_the_configured_postgres_port() -> None:
    quickstart = (ROOT / "specs/001-volunteer-care-report/quickstart.md").read_text()
    compose = (ROOT / "infra/local/docker-compose.yml").read_text()
    assert "65432" in quickstart
    assert '"65432:5432"' in compose
    assert "scripts.seed_local" in quickstart
    assert "tests/e2e/test_line_bot_mvp.py" in quickstart


def test_complete_local_gate_is_documented_across_contract_and_task_artifacts() -> None:
    quickstart = (ROOT / "specs/001-volunteer-care-report/quickstart.md").read_text()
    tasks = (ROOT / "specs/001-volunteer-care-report/tasks.md").read_text()
    gate = ROOT / "scripts/verify_local.sh"

    assert gate.exists()
    assert "scripts/verify_local.sh" in quickstart
    assert "T218" in quickstart and "T224" in quickstart
    assert all(f"T{task}" in tasks for task in ("218", "219", "220", "221", "222", "223", "224"))
    for marker in ("pytest", "ruff", "MinIO", "GCS", "Secret Scan", "Docker Build"):
        assert marker.lower() in gate.read_text().lower()
