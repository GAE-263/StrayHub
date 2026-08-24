import pytest
from pydantic import ValidationError
from services.api.app.api.volunteer_access import (
    VolunteerServiceSummaryItemResponse,
    VolunteerServiceSummaryResponse,
)
from services.api.app.main import app


def test_summary_contract_is_not_yet_exposed_until_item_3_4() -> None:
    """The summary is strict and cannot carry PII or report content."""

    item = VolunteerServiceSummaryItemResponse(
        organization_id="00000000-0000-0000-0000-000000000001",
        organization_name="收容所 A",
        service_date="2026-05-20",
        service_status="recorded",
        record_count=1,
        source="care_report",
    )
    assert VolunteerServiceSummaryResponse(items=[item], next_cursor=None).model_dump()

    with pytest.raises(ValidationError):
        VolunteerServiceSummaryResponse.model_validate(
            {
                "items": [
                    {
                        "organization_id": "00000000-0000-0000-0000-000000000001",
                        "organization_name": "收容所 A",
                        "service_date": "2026-05-20",
                        "service_status": "recorded",
                        "record_count": 1,
                        "source": "care_report",
                        "applicant_name": "不應出現",
                    }
                ],
                "next_cursor": None,
            }
        )


def test_runtime_summary_route_and_schema_are_explicit() -> None:
    document = app.openapi()
    path = document["paths"][
        "/v1/organizations/{organizationId}/volunteer-applications/{applicationId}/service-summary"
    ]["get"]
    assert path["operationId"] == "getVolunteerApplicationServiceSummary"
    purpose = next(
        parameter for parameter in path["parameters"] if parameter["name"] == "purpose_code"
    )
    assert purpose["schema"]["const"] == "volunteer_service_history_review"
    schema = document["components"]["schemas"]["VolunteerServiceSummaryItemResponse"]
    assert schema["additionalProperties"] is False
    assert not {"applicant_name", "phone_number", "answers", "line_user_id"} & set(
        schema["properties"]
    )
