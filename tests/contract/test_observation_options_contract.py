from pathlib import Path

import yaml

CONTRACT = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")


def _document() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def test_observation_vocabulary_exposes_read_and_management_contracts() -> None:
    document = _document()
    paths = document["paths"]
    assert paths["/v1/observation-categories"]["get"]["operationId"] == "listObservationCategories"
    assert paths["/v1/observation-options"]["get"]["operationId"] == "listObservationOptions"
    assert paths["/v1/observation-options"]["post"]["operationId"] == "createObservationOption"
    assert (
        paths["/v1/observation-options/{optionId}"]["patch"]["operationId"]
        == "updateObservationOption"
    )
    assert (
        paths["/v1/observation-options/reorder"]["post"]["operationId"]
        == "reorderObservationOptions"
    )


def test_management_contract_is_failure_first_and_has_no_hard_delete() -> None:
    document = _document()
    paths = document["paths"]
    schemas = document["components"]["schemas"]
    create = schemas["ObservationOptionCreateRequest"]
    assert {"category_id", "code", "display_name"} <= set(create["required"])
    assert "delete" not in paths["/v1/observation-options/{optionId}"]

    for path, method in (
        ("/v1/observation-options", "post"),
        ("/v1/observation-options/{optionId}", "patch"),
        ("/v1/observation-options/reorder", "post"),
    ):
        responses = paths[path][method]["responses"]
        assert "401" in responses
        assert "403" in responses
        assert any(code.startswith(("4", "5")) for code in responses)


def test_option_contract_keeps_stable_code_and_source_metadata() -> None:
    option = _document()["components"]["schemas"]["ObservationOption"]
    assert {"code", "category_id", "status", "enabled", "display_order", "source"} <= set(
        option["required"]
    )
    assert "code" in option["properties"]
    assert "display_name" in option["properties"]
