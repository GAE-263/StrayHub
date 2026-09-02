from uuid import uuid4

import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.management_access import require_staff_or_admin
from services.api.app.application.growth_diary_service import GrowthDiaryManagementService


class _EmptyResult:
    def one_or_none(self):
        return None

    def scalar_one_or_none(self):
        return None


class _EmptySession:
    async def execute(self, _statement):
        return _EmptyResult()


@pytest.mark.parametrize("role", ["STAFF", "SHELTER_ADMIN", "PLATFORM_ADMIN"])
def test_allowed_management_roles_require_an_active_shelter_context(role) -> None:
    organization_id = uuid4()
    context = RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4() if role != "PLATFORM_ADMIN" else None,
        role=role,
        platform_scope=role == "PLATFORM_ADMIN",
    )

    assert require_staff_or_admin(context) == organization_id


def test_volunteer_and_missing_active_context_are_rejected() -> None:
    with pytest.raises(DomainError) as volunteer:
        require_staff_or_admin(RequestContext(uuid4(), uuid4(), uuid4(), "VOLUNTEER"))
    assert (volunteer.value.status_code, volunteer.value.code) == (
        403,
        "management_access_denied",
    )

    with pytest.raises(DomainError) as no_context:
        require_staff_or_admin(RequestContext(uuid4(), None, None, "PLATFORM_ADMIN", True))
    assert (no_context.value.status_code, no_context.value.code) == (
        409,
        "shelter_context_required",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["detail", "photo"])
async def test_other_shelter_and_nonexistent_ids_share_safe_not_found_behavior(operation) -> None:
    service = GrowthDiaryManagementService(_EmptySession(), uuid4())

    with pytest.raises(DomainError) as missing:
        await getattr(service, operation)(uuid4())

    assert (missing.value.status_code, missing.value.code) == (
        404,
        "growth_diary_entry_not_found",
    )
