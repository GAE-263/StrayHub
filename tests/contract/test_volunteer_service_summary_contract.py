import pytest
from pydantic import ValidationError
from services.api.app.api.volunteer_access import VolunteerServiceSummaryResponse
from services.api.app.main import app


def _payload() -> dict:
    return {
        "current_shelter_visits": 3,
        "total_strayhub_visits": 8,
        "visits_last_180_days": 6,
        "visits_last_90_days": 4,
        "visits_last_30_days": 1,
        "last_visit_at": "2026-09-01T10:00:00Z",
        "active_months_last_6_months": 4,
        "recent_status": "consistently_active",
        "has_active_platform_restriction": False,
        "approval_blocked": False,
    }


def test_summary_contract_exposes_aggregate_only() -> None:
    assert VolunteerServiceSummaryResponse.model_validate(_payload())
    with pytest.raises(ValidationError):
        VolunteerServiceSummaryResponse.model_validate(
            {**_payload(), "organization_name": "不應跨所揭露"}
        )


def test_runtime_summary_route_has_no_detail_pagination() -> None:
    path = app.openapi()["paths"][
        "/v1/organizations/{organizationId}/volunteer-applications/{applicationId}/service-summary"
    ]["get"]
    parameter_names = {parameter["name"] for parameter in path["parameters"]}
    assert "purpose_code" in parameter_names
    assert "cursor" not in parameter_names
    assert "limit" not in parameter_names
    schema = app.openapi()["components"]["schemas"]["VolunteerServiceSummaryResponse"]
    assert not {"organization_name", "service_date", "items"} & set(schema["properties"])
