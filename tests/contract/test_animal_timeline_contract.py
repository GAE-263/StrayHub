from pathlib import Path

import yaml

CONTRACT_PATH = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")


def _document() -> dict:
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_timeline_recent_and_date_range_contract_is_explicit() -> None:
    document = _document()
    operation = document["paths"]["/v1/animals/{animalId}/timeline"]["get"]

    assert operation["operationId"] == "getAnimalTimeline"
    assert operation.get("security") or document["security"]
    parameters = {
        parameter.get("name"): parameter
        for parameter in operation["parameters"]
        if "name" in parameter
    }
    assert parameters["start_date"]["schema"] == {"type": "string", "format": "date"}
    assert parameters["end_date"]["schema"] == {"type": "string", "format": "date"}
    assert "required" not in parameters["start_date"]
    assert "required" not in parameters["end_date"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TimelineResponse"
    }
    assert {
        "401",
        "403",
        "404",
        "409",
        "422",
    } <= set(operation["responses"])


def test_timeline_daily_summary_no_report_and_report_details_are_declared() -> None:
    schemas = _document()["components"]["schemas"]
    timeline = schemas["TimelineResponse"]["properties"]["days"]["items"]
    assert {"date", "has_report", "report_count"} <= set(timeline["required"])
    assert {"date", "has_report", "report_count", "no_report_label", "reports"} <= set(
        timeline["properties"]
    )

    assert timeline["properties"]["reports"]["items"] == {
        "$ref": "#/components/schemas/TimelineReport"
    }
    report = schemas["TimelineReport"]
    assert {
        "id",
        "submitted_at",
        "volunteer_user_id",
        "volunteer_label",
        "animal_name_snapshot",
        "shelter_number_snapshot",
        "note",
        "observations",
        "observation_snapshots",
        "status",
        "ai_job_status",
        "media_ids",
        "stool_analysis",
    } <= set(report["properties"])
    assert "volunteer_label" in report["required"]
    assert report["properties"]["stool_analysis"] == {
        "anyOf": [
            {"$ref": "#/components/schemas/StoolAnalysis"},
            {"type": "null"},
        ]
    }
    assert set(schemas["StoolAnalysis"]["required"]) == {
        "recognized",
        "score",
        "score_label",
        "has_abnormalities",
        "abnormality_details",
        "assessment",
        "recommendation",
        "review_status",
        "human_reviewed",
    }
