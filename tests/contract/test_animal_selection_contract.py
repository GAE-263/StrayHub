from pathlib import Path

import yaml
from fastapi.routing import APIRoute
from services.api.app.api.animal_selection import (
    AnimalCandidateResponse,
    AnimalListResponse,
    QrResolveRequest,
    router,
)
from services.api.app.api.care_reports import DraftCreateRequest


def test_animal_selection_router_exposes_all_selection_operations() -> None:
    routes = {
        (route.path, method.upper())
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    assert ("/v1/animals", "GET") in routes
    assert ("/v1/animals/search", "GET") in routes
    assert ("/v1/qr-tokens/resolve", "POST") in routes
    assert ("/v1/animals/{animalId}/confirm", "POST") in routes


def test_animal_selection_contract_preserves_identity_and_disambiguation_fields() -> None:
    fields = AnimalCandidateResponse.model_fields
    assert {"id", "name", "shelter_number", "photo_url", "cage", "area"} <= fields.keys()
    assert fields["organization_id"].is_required()
    assert fields["can_report"].is_required()
    assert AnimalListResponse.model_fields["page"].is_required()
    assert QrResolveRequest.model_fields["qr_token"].is_required()
    assert DraftCreateRequest.model_fields["animal_id"].is_required()
    assert DraftCreateRequest.model_fields["confirmation_token"].is_required()


def test_animal_selection_openapi_declares_consistent_error_and_request_shapes() -> None:
    document = yaml.safe_load(
        Path("specs/001-volunteer-care-report/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    assert "/v1/animals" in paths
    assert "/v1/animals/search" in paths
    assert "/v1/qr-tokens/resolve" in paths
    assert "/v1/animals/{animalId}/confirm" in paths
    assert paths["/v1/qr-tokens/resolve"]["post"]["responses"]["404"]
    assert paths["/v1/animals/{animalId}/confirm"]["post"]["responses"]["403"]
    assert (
        "confirmation_token" in document["components"]["schemas"]["DraftCreateRequest"]["required"]
    )
