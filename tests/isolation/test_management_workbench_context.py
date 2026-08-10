from pathlib import Path


def test_management_queries_keep_organization_scope_in_the_query_boundary() -> None:
    sources = {
        "dashboard": Path("services/api/app/application/dashboard_service.py").read_text(),
        "animals": Path("services/api/app/application/management_animal_service.py").read_text(),
        "reports": Path("services/api/app/api/report_inbox.py").read_text(),
        "audit": Path("services/api/app/api/audit.py").read_text(),
        "qr": Path("services/api/app/api/qr_codes.py").read_text(),
        "scope": Path("services/api/app/api/reportable_scope.py").read_text(),
    }

    for name, source in sources.items():
        assert "organization_id" in source, name
        assert "require_staff_or_admin" in source or name in {"dashboard", "animals"}, name


def test_management_frontend_has_no_first_animal_redirect_or_formal_org_a() -> None:
    home = Path("apps/web/app/management-home.tsx").read_text()
    login = Path("apps/web/app/login/page.tsx").read_text()

    assert "items[0]" not in home
    assert 'code === "ORG-A"' not in login
