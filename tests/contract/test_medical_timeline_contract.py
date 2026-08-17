from services.api.app.main import app


def test_timeline_contract_keeps_legacy_and_additive_medical_care_fields() -> None:
    response = app.openapi()["paths"]["/v1/animals/{animalId}/timeline"]["get"]
    schema = response["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("#/components/schemas/TimelineResponse")
    timeline = app.openapi()["components"]["schemas"]["TimelineResponse"]["properties"]
    assert {"animal_id", "organization_timezone", "days", "open_reminders"} <= set(timeline)
    day = app.openapi()["components"]["schemas"]["TimelineDayResponse"]["properties"]
    assert {"has_report", "has_activity", "events", "scheduled"} <= set(day)
    event = app.openapi()["components"]["schemas"]["TimelineEventResponse"]["properties"]
    assert event["occurrence"]["enum"] == ["actual", "scheduled"]


def test_timeline_contract_declares_local_date_query_parameters() -> None:
    parameters = app.openapi()["paths"]["/v1/animals/{animalId}/timeline"]["get"]["parameters"]
    assert {item["name"] for item in parameters} >= {"start_date", "end_date"}
