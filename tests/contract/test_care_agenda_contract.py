from services.api.app.main import app


def test_agenda_and_calendar_paths_expose_timezone_and_four_buckets() -> None:
    schema = app.openapi()
    assert "/v1/management/care-agenda" in schema["paths"]
    assert "/v1/management/care-calendar" in schema["paths"]
    agenda = schema["components"]["schemas"]["CareAgendaResponse"]
    assert set(agenda["required"]) >= {
        "timezone",
        "timezone_version",
        "local_today",
        "buckets",
        "totals",
        "pages",
    }
    assert agenda["properties"]["buckets"]["additionalProperties"]["type"] == "array"
    parameters = schema["paths"]["/v1/management/care-agenda"]["get"]["parameters"]
    names = {parameter["name"] for parameter in parameters}
    assert {
        "page_size",
        "today_pending_cursor",
        "overdue_cursor",
        "today_resolved_cursor",
        "next_seven_days_cursor",
    } <= names
