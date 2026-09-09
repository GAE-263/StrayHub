from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_remote_management_resource_families_retain_real_database_rls() -> None:
    """Phase E acceptance reuses the canonical real-PostgreSQL A/B matrix."""

    from tests.isolation.test_cross_tenant_resource_matrix import (
        test_a_b_resource_matrix_hides_business_resources_and_signed_media,
    )

    await test_a_b_resource_matrix_hides_business_resources_and_signed_media()


def test_remote_registry_never_exposes_client_selected_tenant_scope() -> None:
    from scripts.public_tunnel_policy import compile_profile

    profile, _ = compile_profile(
        "shared-demo-production",
        build_dir=Path("tests/security/fixtures/next-manifests"),
        runtime_origin="http://127.0.0.1:8082",
        allow_loopback_for_test=True,
    )
    routes = {route.id: route for route in profile.routes}
    for route_id in (
        "management_animals_api",
        "management_animal_detail_api",
        "management_animal_photo_api",
        "animal_timeline_api",
        "management_reports_api",
        "management_report_detail_api",
        "management_care_calendar_api",
        "management_care_agenda_api",
    ):
        assert routes[route_id].authentication == "bearer_session_public_profile_role_and_tenant"
