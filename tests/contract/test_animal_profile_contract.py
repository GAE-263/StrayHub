from pathlib import Path

import yaml
from services.api.app.main import app


def _shape(schema):
    schema = {key: value for key, value in schema.items() if key not in {"title", "description"}}
    if schema.get("default") is None:
        schema.pop("default", None)
    if "anyOf" in schema:
        alternatives = schema.pop("anyOf")
        non_null = next(item for item in alternatives if item.get("type") != "null")
        schema.update(non_null)
        schema["type"] = [schema["type"], "null"]
    return schema


def test_profile_canonical_runtime_and_generated_contract_parity():
    canonical = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    runtime = app.openapi()
    for name in (
        "AnimalProfileUpdate",
        "ManagementAnimal",
        "ManagementAnimalResponse",
        "ManagementAnimalListResponse",
    ):
        expected = canonical["components"]["schemas"][name]
        actual = runtime["components"]["schemas"][name]
        assert set(expected.get("required", [])) == set(actual.get("required", []))
        assert expected.get("additionalProperties") == actual.get("additionalProperties")
        assert set(expected["properties"]) == set(actual["properties"])
        for field in expected["properties"]:
            assert _shape(expected["properties"][field]) == _shape(actual["properties"][field]), (
                name,
                field,
            )
    for field in (
        "sex",
        "breed",
        "birth_date",
        "birth_date_estimated",
        "age_description",
        "care_guidance",
    ):
        assert _shape(
            canonical["components"]["schemas"]["AnimalCandidate"]["properties"][field]
        ) == _shape(
            runtime["components"]["schemas"]["AnimalCandidateResponse"]["properties"][field]
        )
    for name in ("AnimalCandidateResponse", "AnimalConfirmationResponse"):
        assert "behavior_notes" not in runtime["components"]["schemas"][name]["properties"]
    operation = runtime["paths"]["/v1/management/animals/{animal_id}/profile"]["patch"]
    expected_operation = canonical["paths"]["/v1/management/animals/{animalId}/profile"]["patch"]
    assert operation["operationId"] == expected_operation["operationId"]
    assert set(operation["responses"]) == set(expected_operation["responses"])
    for status in ("401", "403", "404", "409", "422"):
        response_name = expected_operation["responses"][status]["$ref"].rsplit("/", 1)[1]
        expected_response = canonical["components"]["responses"][response_name]
        assert operation["responses"][status]["content"] == expected_response["content"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/AnimalProfileUpdate"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ManagementAnimalResponse"
    )
    generated = Path("packages/contracts/src/openapi.ts").read_text()
    assert '"/v1/management/animals/{animalId}/profile"' in generated
    assert "AnimalProfileUpdate:" in generated


def test_management_animal_photo_contract_is_authenticated_binary_and_private():
    canonical = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    runtime = app.openapi()
    canonical_path = "/v1/management/animals/{animalId}/photo"
    runtime_path = "/v1/management/animals/{animal_id}/photo"

    operation = canonical["paths"][canonical_path]["get"]
    assert operation["security"] == [{"bearerAuth": []}]
    assert set(operation["responses"]) == {"200", "304", "401", "403", "404", "409"}
    assert {parameter.get("name") for parameter in operation["parameters"]} >= {
        "v",
        "If-None-Match",
    }
    assert set(operation["responses"]["200"]["content"]) == {
        "image/jpeg",
        "image/png",
        "image/webp",
    }
    assert (
        operation["responses"]["200"]["headers"]["Cache-Control"]["schema"]["const"]
        == "private, max-age=300, must-revalidate"
    )
    assert "ETag" in operation["responses"]["200"]["headers"]
    assert (
        operation["responses"]["200"]["headers"]["Vary"]["schema"]["const"]
        == "Authorization, X-Session-ID"
    )
    assert (
        operation["responses"]["200"]["headers"]["X-Content-Type-Options"]["schema"]["const"]
        == "nosniff"
    )

    runtime_operation = runtime["paths"][runtime_path]["get"]
    assert runtime_operation["operationId"] == operation["operationId"]
    assert "304" in runtime_operation["responses"]
    assert set(runtime_operation["responses"]["200"]["content"]) == set(
        operation["responses"]["200"]["content"]
    )
