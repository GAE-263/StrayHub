import pytest
from services.api.app.api.animal_selection import router as animal_selection_router
from services.api.app.api.animal_timeline import router as animal_timeline_router
from services.api.app.api.care_reports import router as care_reports_router
from services.api.app.api.dependencies import _load_request_context
from services.api.app.api.errors import DomainError
from services.api.app.api.media import router as media_router


@pytest.mark.asyncio
async def test_missing_authentication_cannot_load_internal_request_context() -> None:
    with pytest.raises(DomainError, match="請先完成身分驗證"):
        await _load_request_context(object(), authorization=None, session_id=None)


def test_internal_routes_require_server_request_context() -> None:
    protected_prefixes = ("/v1/animals", "/v1/care-reports", "/v1/timeline", "/v1/media")
    routers = [
        animal_selection_router,
        animal_timeline_router,
        care_reports_router,
        media_router,
    ]
    protected_routes = [
        route
        for router in routers
        for route in router.routes
        if route.path.startswith(protected_prefixes)
    ]

    assert protected_routes
    for route in protected_routes:
        dependency_callables = {
            dependency.call
            for dependency in route.dependant.dependencies
            if dependency.call is not None
        }
        assert any(
            callable.__name__ == "current_request_context" for callable in dependency_callables
        )
