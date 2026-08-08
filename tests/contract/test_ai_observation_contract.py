from pathlib import Path

import yaml

CONTRACT_PATH = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")


def test_ai_observation_contract_exposes_traceable_status_and_version_metadata() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    schema = document["components"]["schemas"]["AiObservation"]

    assert {
        "id",
        "job_id",
        "status",
        "source_type",
        "source_id",
        "provider",
        "model_name",
        "model_version",
        "prompt_template_id",
        "prompt_version",
        "output_schema_version",
        "raw_ai_output",
        "validated_ai_observation",
        "human_review_result",
    } <= set(schema["required"])
    assert set(schema["properties"]["status"]["enum"]) >= {
        "pending",
        "running",
        "succeeded",
        "failed",
        "invalid",
        "confirmed",
        "rejected",
        "corrected",
    }
    assert schema["properties"]["source_type"]["enum"] == ["note", "photo"]


def test_ai_review_contract_supports_confirm_reject_and_correct() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    request = document["components"]["schemas"]["AiReviewRequest"]
    assert set(request["properties"]["action"]["enum"]) == {"confirm", "reject", "correct"}
    assert "reason" in request["required"]
    assert "corrected_observation" in request["properties"]


def test_ai_observation_errors_are_declared_on_review_and_read_paths() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    paths = document["paths"]

    review = paths["/v1/ai-observations/{observationId}/review"]["post"]
    assert {"401", "403", "404", "422"} <= set(review["responses"])
    listing = paths["/v1/care-reports/{reportId}/ai-observations"]["get"]
    assert {"401", "403", "404"} <= set(listing["responses"])
