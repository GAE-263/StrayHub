from fastapi.routing import APIRoute
from services.api.app.main import app


def test_management_routes_are_registered_as_a_single_api_surface() -> None:
    paths = set(app.openapi()["paths"])

    assert {
        "/v1/management/dashboard",
        "/v1/management/animals",
        "/v1/management/animals/{animal_id}",
        "/v1/management/reports",
        "/v1/management/reports/{report_id}",
        "/v1/management/reportable-scopes",
        "/v1/management/qr-codes",
        "/v1/management/audit",
        "/v1/management/ai-review",
    } <= paths


def test_management_routes_have_context_dependencies() -> None:
    app.openapi()

    def routes(router) -> list[APIRoute]:
        found: list[APIRoute] = []
        for route in router.routes:
            if isinstance(route, APIRoute):
                found.append(route)
            elif hasattr(route, "original_router"):
                found.extend(routes(route.original_router))
        return found

    management_routes = [
        route for route in routes(app.router) if route.path.startswith("/v1/management/")
    ]

    assert management_routes
    assert all(route.dependant.dependencies for route in management_routes)
