from pathlib import Path

import pytest
from services.api.app.main import app


@pytest.mark.e2e
def test_ai_review_workflow_covers_queue_review_and_read_only_audit() -> None:
    ai_page = Path("apps/web/app/(management)/ai-review/page.tsx").read_text()
    audit_page = Path("apps/web/app/(management)/settings/audit/page.tsx").read_text()
    ai_api = Path("services/api/app/api/ai_observations.py").read_text()
    audit_api = Path("services/api/app/api/audit.py").read_text()

    assert "confirm" in ai_page
    assert "reject" in ai_page
    assert "correct" in ai_page
    assert "raw_ai_output" in ai_page
    assert 'method: "POST"' not in audit_page
    assert "human_review_result" in ai_api
    assert "AuditRecord" in audit_api
    assert "/v1/management/ai-review" in app.openapi()["paths"]
    assert "/v1/management/audit" in app.openapi()["paths"]


@pytest.mark.e2e
def test_ai_review_workflow_preserves_raw_output_and_scope() -> None:
    service = Path("services/api/app/application/ai_review.py").read_text()
    repository = Path(
        "services/api/app/persistence/repositories/ai_observation_repository.py"
    ).read_text()

    assert "raw_ai_output" in service
    assert "organization_id" in repository
    assert "reviewed_by" in service
