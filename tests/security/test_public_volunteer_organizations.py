from __future__ import annotations

import inspect
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from services.api.app.api import volunteer_access as api
from services.api.app.persistence.repositories.organization_repository import (
    OrganizationRepository,
)

SCOPE_MODULE = Path("services/api/app/persistence/database/scope.py")
PUBLIC_DIRECTORY_MIGRATION = Path(
    "services/api/migrations/versions/0032_public_volunteer_directory_scope.py"
)


def test_public_response_has_exactly_the_minimum_directory_fields() -> None:
    response_model = api.PublicVolunteerOrganizationResponse

    assert set(response_model.model_fields) == {
        "id",
        "code",
        "name",
        "service_area",
        "insurance_required",
    }

    with pytest.raises(ValidationError):
        response_model.model_validate(
            {
                "id": uuid4(),
                "code": "ORG-SYNTHETIC",
                "name": "Synthetic Shelter",
                "service_area": None,
                "insurance_required": False,
                "address": "must-not-leak",
                "contact": "must-not-leak",
                "status": "active",
                "membership": {},
                "users": [],
                "applications": [],
                "animals": [],
            }
        )


def test_public_route_does_not_accept_client_organization_selector_or_private_context() -> None:
    route = next(
        route
        for route in api.router.routes
        if getattr(route, "path", None) == "/v1/public/volunteer-organizations"
    )
    parameter_names = set(inspect.signature(route.endpoint).parameters)

    assert parameter_names == {"session"}
    assert "organization_id" not in parameter_names
    assert "organization_code" not in parameter_names
    assert "context" not in parameter_names


def test_public_repository_contract_is_a_narrow_projection_without_private_tables() -> None:
    source = inspect.getsource(OrganizationRepository.list_public_volunteer_organizations)

    assert "select(" in source
    assert "Organization.id," in source
    assert "OrganizationVolunteerAccessPolicy.insurance_required" in source
    assert 'Organization.status == "active"' in source
    assert "OrganizationVolunteerAccessPolicy.applications_enabled.is_(True)" in source
    assert "order_by(Organization.name, Organization.code, Organization.id)" in source
    assert "OrganizationMembership" not in source
    assert "VolunteerApplication" not in source
    assert "Animal" not in source
    assert "text(" not in source
    assert "set_public_volunteer_directory_scope(self.session)" in source


def test_public_query_predicate_names_active_and_enabled_organizations_only() -> None:
    source = inspect.getsource(OrganizationRepository.list_public_volunteer_organizations)

    assert 'Organization.status == "active"' in source
    assert "OrganizationVolunteerAccessPolicy.applications_enabled.is_(True)" in source


def test_public_directory_has_a_dedicated_transaction_local_scope_helper() -> None:
    source = SCOPE_MODULE.read_text()

    assert "async def set_public_volunteer_directory_scope(" in source
    helper = source[source.index("async def set_public_volunteer_directory_scope(") :]
    assert "await set_platform_scope(session)" in helper
    assert "app.public_volunteer_directory" in helper
    assert "set_config('app.public_volunteer_directory', 'true', true)" in helper


def test_public_directory_migration_allows_public_select_but_keeps_writes_tenant_only() -> None:
    assert PUBLIC_DIRECTORY_MIGRATION.exists()
    migration = PUBLIC_DIRECTORY_MIGRATION.read_text()

    assert 'revision = "0032_public_volunteer_directory_scope"' in migration
    assert 'down_revision = "0031_volunteer_insurance_policy"' in migration
    assert "DROP POLICY organization_volunteer_access_policies_tenant_scope" in migration
    select_start = migration.index(
        "CREATE POLICY organization_volunteer_access_policies_public_select"
    )
    insert_start = migration.index(
        "CREATE POLICY organization_volunteer_access_policies_tenant_insert"
    )
    update_start = migration.index(
        "CREATE POLICY organization_volunteer_access_policies_tenant_update"
    )
    delete_start = migration.index(
        "CREATE POLICY organization_volunteer_access_policies_tenant_delete"
    )
    downgrade_start = migration.index("def downgrade")
    select_policy = migration[select_start:insert_start]
    write_policies = migration[insert_start:downgrade_start]
    assert "FOR SELECT" in select_policy
    assert "app.platform_scope" in select_policy
    assert "app.public_volunteer_directory" in select_policy
    assert "FOR INSERT" in write_policies
    assert "FOR UPDATE" in write_policies
    assert "FOR DELETE" in write_policies
    assert "app.public_volunteer_directory" not in write_policies
    assert delete_start > update_start > insert_start
    assert migration.count("NULLIF(current_setting('app.current_org_id', true), '')") >= 5
    assert (
        "CREATE POLICY organization_volunteer_access_policies_tenant_scope"
        in migration[downgrade_start:]
    )
