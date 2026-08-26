from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.routing import APIRoute
from services.api.app.api.care_report_handoffs import (
    CareReportHandoffCreateRequest,
    CareReportHandoffResponse,
    router,
)
from services.api.app.application.care_report_handoff_service import (
    CareReportHandoffService,
)

CONTRACT_PATH = Path("specs/001-volunteer-care-report/contracts/openapi.yaml")


def test_handoff_router_exposes_create_only() -> None:
    routes = {
        (route.path, method.upper())
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }

    assert routes == {("/v1/care-report-handoffs", "POST")}


def test_create_contract_accepts_confirmation_context_but_not_identity_scope() -> None:
    fields = CareReportHandoffCreateRequest.model_fields

    assert set(fields) == {"animal_id", "confirmation_token", "source"}
    assert CareReportHandoffCreateRequest.model_config["extra"] == "forbid"
    assert {"user_id", "organization_id", "membership_id", "handoff_id"}.isdisjoint(fields)
    assert set(CareReportHandoffResponse.model_fields) == {"id", "status", "expires_at"}


def test_consume_boundary_accepts_no_message_identifiers() -> None:
    fields = CareReportHandoffService.consume_pending_handoff.__annotations__

    assert {"user_id", "organization_id"} <= fields.keys()
    assert {"animal_id", "handoff_id", "confirmation_token"}.isdisjoint(fields)


def test_openapi_declares_minimal_handoff_contract() -> None:
    document = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    operation = document["paths"]["/v1/care-report-handoffs"]["post"]
    schemas = document["components"]["schemas"]
    request = schemas["CareReportHandoffCreateRequest"]
    response = schemas["CareReportHandoffResponse"]

    assert operation["operationId"] == "createOrReplaceCareReportHandoff"
    assert operation["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CareReportHandoffResponse"
    }
    assert request["additionalProperties"] is False
    assert set(request["required"]) == {"animal_id", "confirmation_token", "source"}
    assert {"user_id", "organization_id", "membership_id", "handoff_id"}.isdisjoint(
        request["properties"]
    )
    assert set(response["properties"]) == {"id", "status", "expires_at"}
    assert response["properties"]["status"]["enum"] == ["pending"]
