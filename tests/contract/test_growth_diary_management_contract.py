from pathlib import Path

import yaml
from services.api.app.main import app

FEATURE_CONTRACT = Path(
    "specs/011-growth-diary-management/contracts/growth-diary-management.openapi.yaml"
)
LIST_PATH = "/v1/management/growth-diary-entries"
DETAIL_PATH = "/v1/management/growth-diary-entries/{entryId}"
PHOTO_PATH = "/v1/management/growth-diary-entries/{entryId}/photo"
PHOTOS_PATH = "/v1/management/growth-diary-entries/{entryId}/photos/{index}"
STATUS_PATH = "/v1/management/growth-diary-entries/{entryId}/status"


def _contract() -> dict:
    return yaml.safe_load(FEATURE_CONTRACT.read_text(encoding="utf-8"))


def test_growth_diary_feature_contract_declares_scoped_read_and_status_paths() -> None:
    document = _contract()

    assert document["openapi"].startswith("3.")
    assert set(document["paths"]) == {
        LIST_PATH,
        DETAIL_PATH,
        PHOTO_PATH,
        PHOTOS_PATH,
        STATUS_PATH,
    }
    for path_item in document["paths"].values():
        operation = next(iter(path_item.values()))
        assert operation["security"] == [{"bearerAuth": []}]


def test_list_query_bounds_and_response_shape_are_explicit() -> None:
    document = _contract()
    operation = document["paths"][LIST_PATH]["get"]
    parameters = {parameter["name"]: parameter["schema"] for parameter in operation["parameters"]}

    assert parameters["query"]["maxLength"] == 120
    assert parameters["mood"]["enum"] == [
        "all",
        "concern",
        "positive",
        "neutral",
        "unanalyzed",
    ]
    assert parameters["status"]["enum"] == ["all", "new", "reviewed"]
    assert parameters["from_date"]["format"] == "date"
    assert parameters["to_date"]["format"] == "date"
    assert parameters["page"] == {"type": "integer", "minimum": 1, "default": 1}
    assert parameters["page_size"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "default": 50,
    }
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/GrowthDiaryListResponse")


def test_list_excludes_raw_output_while_detail_requires_provenance() -> None:
    schemas = _contract()["components"]["schemas"]
    list_item = schemas["GrowthDiaryListItem"]
    detail_extension = schemas["GrowthDiaryDetail"]["allOf"][1]

    assert "ai_raw_output" not in list_item["properties"]
    assert "ai_provenance" not in list_item["properties"]
    assert set(detail_extension["required"]) == {"ai_provenance", "ai_raw_output"}
    assert detail_extension["properties"]["ai_provenance"]["$ref"].endswith(
        "/GrowthDiaryAiProvenance"
    )
    raw_output = detail_extension["properties"]["ai_raw_output"]["oneOf"]
    assert {variant["type"] for variant in raw_output} == {"object", "string", "null"}


def test_nullable_fields_and_safe_error_schema_are_explicit() -> None:
    schemas = _contract()["components"]["schemas"]
    list_item = schemas["GrowthDiaryListItem"]
    ai_summary = schemas["GrowthDiaryAiSummary"]
    provenance = schemas["GrowthDiaryAiProvenance"]

    for field in ("animal_name", "shelter_number", "photo_endpoint", "note"):
        assert "null" in list_item["properties"][field]["type"]
    for field in ("mood", "adopter_reply", "staff_summary"):
        assert "null" in ai_summary["properties"][field]["type"]
    for field in (
        "provider",
        "model_name",
        "model_version",
        "prompt_version",
        "output_schema_version",
        "analyzed_at",
    ):
        assert "null" in provenance["properties"][field]["type"]

    error = schemas["ErrorResponse"]
    assert error["required"] == ["code", "message"]
    assert set(error["properties"]) == {"code", "message"}
    for operation in (
        _contract()["paths"][LIST_PATH]["get"],
        _contract()["paths"][DETAIL_PATH]["get"],
        _contract()["paths"][PHOTO_PATH]["get"],
    ):
        for status, response in operation["responses"].items():
            if status.startswith("4"):
                assert response["$ref"].endswith("/Error")


def test_photo_contract_uses_webp_content_and_only_security_headers() -> None:
    response = _contract()["paths"][PHOTO_PATH]["get"]["responses"]["200"]

    assert set(response["content"]) == {"image/webp"}
    assert response["content"]["image/webp"]["schema"] == {
        "type": "string",
        "contentEncoding": "binary",
    }
    assert "Content-Type" not in response["headers"]
    assert response["headers"]["Cache-Control"]["schema"]["const"] == "private, no-store"
    assert response["headers"]["X-Content-Type-Options"]["schema"]["const"] == "nosniff"


def test_runtime_openapi_exposes_list_detail_and_webp_photo_contracts() -> None:
    runtime = app.openapi()
    feature = _contract()

    for path in (LIST_PATH, DETAIL_PATH, PHOTO_PATH, PHOTOS_PATH, STATUS_PATH):
        assert path in runtime["paths"]
    assert set(runtime["paths"][STATUS_PATH]) == {"patch"}

    list_schema = runtime["paths"][LIST_PATH]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    detail_schema = runtime["paths"][DETAIL_PATH]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert list_schema["$ref"].endswith("/GrowthDiaryListResponse")
    assert detail_schema["$ref"].endswith("/GrowthDiaryDetail")

    photo_response = runtime["paths"][PHOTO_PATH]["get"]["responses"]["200"]
    assert set(photo_response["content"]) == {"image/webp"}
    assert "Content-Type" not in photo_response.get("headers", {})

    feature_schemas = feature["components"]["schemas"]
    runtime_schemas = runtime["components"]["schemas"]

    def feature_required(schema: dict) -> set[str]:
        required = set(schema.get("required", []))
        for item in schema.get("allOf", []):
            if "$ref" in item:
                required |= feature_required(feature_schemas[item["$ref"].rsplit("/", 1)[-1]])
            else:
                required |= feature_required(item)
        return required

    for schema_name in (
        "GrowthDiaryAiSummary",
        "GrowthDiaryAiProvenance",
        "GrowthDiaryListItem",
        "GrowthDiaryDetail",
        "GrowthDiaryListResponse",
    ):
        assert schema_name in runtime_schemas
        assert set(runtime_schemas[schema_name].get("required", [])) == feature_required(
            feature_schemas[schema_name]
        )
