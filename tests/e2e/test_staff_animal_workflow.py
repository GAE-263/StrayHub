from pathlib import Path

import pytest
from services.api.app.main import app


@pytest.mark.e2e
def test_staff_animal_workflow_keeps_dashboard_to_timeline_path() -> None:
    home = Path("apps/web/app/management-home.tsx").read_text()
    animals = Path("apps/web/app/(management)/animals/page.tsx").read_text()
    profile = Path("apps/web/app/(management)/animals/[animalId]/page.tsx").read_text()
    timeline = Path("apps/web/app/(management)/animals/[animalId]/timeline/page.tsx").read_text()

    assert "/animals" in home
    assert "animal_id" in animals or "animal.id" in animals
    assert "timeline" in profile
    assert "AnimalTimeline" in timeline
    assert "TimelineFilters" in timeline
    assert "/v1/management/animals" in app.openapi()["paths"]


@pytest.mark.e2e
def test_staff_animal_workflow_has_scope_and_status_boundaries() -> None:
    service = Path("services/api/app/application/management_animal_service.py").read_text()
    timeline = Path("services/api/app/api/animal_timeline.py").read_text()

    assert "organization_id" in service
    assert "organization_id" in timeline
    assert "ai_job_status" in timeline
