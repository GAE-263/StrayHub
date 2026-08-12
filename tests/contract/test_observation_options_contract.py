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
    assert paths["/v1/observation-options/{optionId}/disable"]["post"]["operationId"] == (
        "disableObservationOption"
    )
    assert paths["/v1/observation-options/{optionId}/restore"]["post"]["operationId"] == (
        "restoreObservationOption"
    )
    assert paths["/v1/observation-options/{optionId}/archive"]["post"]["operationId"] == (
        "archiveObservationOption"
    )


def test_management_contract_is_failure_first_and_has_no_hard_delete() -> None:
    document = _document()
    paths = document["paths"]
    schemas = document["components"]["schemas"]
    create = schemas["ObservationOptionCreateRequest"]
    update = schemas["ObservationOptionUpdateRequest"]
    assert {"category_id", "code", "display_name"} <= set(create["required"])
    assert update["required"] == ["expected_updated_at"]
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
    assert set(option["properties"]["status"]["enum"]) == {
        "active",
        "disabled",
        "archived",
    }
    assert {"has_historical_usage", "historical_usage_count"} <= set(option["properties"])


def test_observation_audit_contract_has_operation_grouping_and_resource_filter() -> None:
    document = _document()
    audit_path = document["paths"]["/v1/management/audit"]
    parameter_names = {item.get("name") for item in audit_path["get"]["parameters"]}
    assert "resource_id" in parameter_names
    audit = document["components"]["schemas"]["ManagementAuditRecord"]
    assert {"operation_id", "result", "before", "after"} <= set(audit["properties"])
