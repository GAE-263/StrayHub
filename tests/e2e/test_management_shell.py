from pathlib import Path

import pytest
from services.api.app.main import app


@pytest.mark.e2e
def test_management_shell_vertical_surface_covers_auth_context_and_navigation() -> None:
    layout = Path("apps/web/components/management/ManagementLayout.tsx").read_text()
    header = Path("apps/web/components/management/AppHeader.tsx").read_text()
    sidebar = Path("apps/web/components/management/AppSidebar.tsx").read_text()

    assert "active-shelter-context" in layout
    assert "strayhub:context-required" in layout
    assert "onLogout" in header
    assert '"/animals"' in sidebar
    assert '"/reports"' in sidebar
    assert '"/settings/audit"' in sidebar

    paths = app.openapi()["paths"]
    assert "/v1/auth/login" in paths
    assert "/v1/auth/logout" in paths
    assert "/v1/auth/active-shelter-context" in paths
    assert "/v1/management/dashboard" in paths


@pytest.mark.e2e
def test_management_shell_has_failure_first_session_boundaries() -> None:
    layout = Path("apps/web/components/management/ManagementLayout.tsx").read_text()
    api = Path("apps/web/lib/api.ts").read_text()

    assert 'router.replace("/login")' in layout
    assert "clearAuth()" in layout
    assert "status !== 401" in api
    assert "status === 409" in api
