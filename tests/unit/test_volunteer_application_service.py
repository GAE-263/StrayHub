from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_access_service import (
    VolunteerAccessService,
    effective_application_status,
)
from services.api.app.domain.volunteer_access import ENTRY_REFERENCE_PURPOSE

NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)


def test_effective_status_and_next_actions_cover_onboarding_states() -> None:
    assert effective_application_status(None, None, now=NOW) == ("none", ["apply"])
    assert effective_application_status(SimpleNamespace(status="pending"), None, now=NOW) == (
        "pending",
        ["wait", "withdraw"],
    )
    assert effective_application_status(SimpleNamespace(status="rejected"), None, now=NOW) == (
        "rejected",
        ["reapply", "contact_shelter"],
    )
    grant = SimpleNamespace(
        status="active",
        valid_from=NOW + timedelta(hours=1),
        expires_at=NOW + timedelta(days=7),
    )
    assert effective_application_status(SimpleNamespace(status="approved"), grant, now=NOW) == (
        "upcoming",
        ["wait"],
    )


@pytest.mark.asyncio
async def test_status_unknown_identity_does_not_persist_user_binding_or_membership() -> None:
    class Verifier:
        async def verify(self, token):
            return "Uunknown"

    class Repository:
        organization_id = uuid4()
        added = []

        async def policy(self):
            return SimpleNamespace(applications_enabled=True, insurance_required=False)

        async def applications_for_user(self, user_id):
            raise AssertionError("unknown identity must not query applicant history")

    class Identity:
        async def get_line_binding(self, line_user_id):
            return None

        async def get_organization(self, organization_id):
            return SimpleNamespace(id=organization_id, name="測試收容所", status="active")

    service = VolunteerAccessService(Repository(), Identity(), Verifier())
    response = await service.status(id_token="token", entry_reference_id=uuid4())

    assert response.effective_status == "none"
    assert response.application is None
    assert Repository.added == []


def test_entry_purpose_is_fixed_and_blank_reference_is_rejected() -> None:
    assert ENTRY_REFERENCE_PURPOSE == "volunteer_application_entry"
    with pytest.raises(DomainError, match="入口"):
        VolunteerAccessService.validate_entry_reference("")


class _FactoryRepository:
    def __init__(
        self,
        organization_id: UUID,
        *,
        applications_enabled: bool = True,
        insurance_required: bool = False,
    ) -> None:
        self.organization_id = organization_id
        self.applications_enabled = applications_enabled
        self.insurance_required = insurance_required
        self.policy_calls = 0
        # These values model untrusted context that must never become the public source.
        self.client_organization_code = "CLIENT-CODE"
        self.client_organization_name = "Client supplied name"

    async def policy(self):
        self.policy_calls += 1
        return SimpleNamespace(
            applications_enabled=self.applications_enabled,
            insurance_required=self.insurance_required,
        )


class _FactoryAuthenticationRepository:
    def __init__(self, organization) -> None:
        self.organization = organization
        self.organization_calls: list[UUID] = []
        self.line_binding_calls = 0

    async def get_organization(self, organization_id: UUID):
        self.organization_calls.append(organization_id)
        if self.organization is None or self.organization.id != organization_id:
            return None
        return self.organization

    async def get_line_binding(self, _line_user_id):
        self.line_binding_calls += 1
        return None


class _FactoryVerifier:
    async def verify(self, _token: str) -> str:
        return "line-user-for-factory-test"


@pytest.mark.asyncio
async def test_for_organization_uses_database_display_data_as_source_of_truth() -> None:
    organization_id = uuid4()
    repository = _FactoryRepository(organization_id)
    identities = _FactoryAuthenticationRepository(
        SimpleNamespace(
            id=organization_id,
            name="DB source-of-truth shelter",
            code="DB-CODE",
            status="active",
        )
    )
    verifier = _FactoryVerifier()
    audit = object()
    notifications = object()

    service = await VolunteerAccessService.for_organization(
        organization_id,
        repository,
        identities,
        verifier,
        audit=audit,
        notifications=notifications,
    )

    assert service.repository is repository
    assert service.identities is identities
    assert service.verifier is verifier
    assert service.audit is audit
    assert service.notifications is notifications
    assert identities.organization_calls == [organization_id]

    result = await service.status(id_token="token", entry_reference_id=uuid4())
    assert result.organization.id == organization_id
    assert result.organization.name == "DB source-of-truth shelter"
    assert result.organization.applications_enabled is True


@pytest.mark.asyncio
async def test_for_organization_rejects_inactive_database_organization() -> None:
    organization_id = uuid4()
    repository = _FactoryRepository(organization_id)
    identities = _FactoryAuthenticationRepository(
        SimpleNamespace(
            id=organization_id, name="Inactive shelter", code="INACTIVE", status="suspended"
        )
    )

    with pytest.raises(DomainError) as exc_info:
        await VolunteerAccessService.for_organization(
            organization_id, repository, identities, _FactoryVerifier()
        )

    assert exc_info.value.code == "entry_unavailable"
    assert exc_info.value.status_code == 403
    assert repository.policy_calls == 0


@pytest.mark.asyncio
async def test_for_organization_rejects_disabled_volunteer_applications() -> None:
    organization_id = uuid4()
    repository = _FactoryRepository(organization_id, applications_enabled=False)
    identities = _FactoryAuthenticationRepository(
        SimpleNamespace(id=organization_id, name="Enabled shelter", code="ENABLED", status="active")
    )

    with pytest.raises(DomainError) as exc_info:
        await VolunteerAccessService.for_organization(
            organization_id, repository, identities, _FactoryVerifier()
        )

    assert exc_info.value.code == "volunteer_applications_disabled"
    assert exc_info.value.status_code == 403
    assert repository.policy_calls == 1


@pytest.mark.asyncio
async def test_status_factory_allows_disabled_organization_for_status_only() -> None:
    organization_id = uuid4()
    repository = _FactoryRepository(organization_id, applications_enabled=False)
    identities = _FactoryAuthenticationRepository(
        SimpleNamespace(
            id=organization_id, name="Disabled shelter", code="DISABLED", status="active"
        )
    )
    verifier = _FactoryVerifier()

    service = await VolunteerAccessService.for_organization_status(
        organization_id, repository, identities, verifier
    )
    result = await service.status(id_token="token", entry_reference_id=None)

    assert result.organization.applications_enabled is False
    assert result.effective_status == "none"
    assert result.next_actions == ["return_to_line"]
    assert repository.policy_calls == 2


@pytest.mark.asyncio
async def test_status_uses_preverified_line_identity_without_verifying_again() -> None:
    class Verifier:
        calls = 0

        async def verify(self, _token):
            self.calls += 1
            return "unexpected-second-verification"

    class Repository:
        organization_id = uuid4()

        async def policy(self):
            return SimpleNamespace(applications_enabled=True, insurance_required=False)

        async def applications_for_user(self, _user_id):
            raise AssertionError("unknown binding should not load application history")

    class Identity:
        async def get_organization(self, organization_id):
            return SimpleNamespace(id=organization_id, name="Shelter", status="active")

        async def get_line_binding(self, line_user_id):
            assert line_user_id == "verified-line-user"
            return None

    verifier = Verifier()
    result = await VolunteerAccessService(Repository(), Identity(), verifier).status(
        id_token="token",
        entry_reference_id=None,
        verified_line_user_id="verified-line-user",
    )

    assert result.effective_status == "none"
    assert verifier.calls == 0


@pytest.mark.asyncio
async def test_for_organization_rejects_cross_tenant_repository_before_database_lookup() -> None:
    target_organization_id = uuid4()
    repository = _FactoryRepository(uuid4())
    identities = _FactoryAuthenticationRepository(
        SimpleNamespace(
            id=target_organization_id,
            name="Target shelter",
            code="TARGET",
            status="active",
        )
    )

    with pytest.raises(DomainError) as exc_info:
        await VolunteerAccessService.for_organization(
            target_organization_id, repository, identities, _FactoryVerifier()
        )

    assert exc_info.value.code == "organization_scope_mismatch"
    assert exc_info.value.status_code == 404
    assert identities.organization_calls == []
    assert repository.policy_calls == 0


@pytest.mark.asyncio
async def test_for_organization_rejects_non_uuid_target_as_unavailable_scope() -> None:
    organization_id = uuid4()
    repository = _FactoryRepository(organization_id)
    identities = _FactoryAuthenticationRepository(None)

    with pytest.raises(DomainError) as exc_info:
        await VolunteerAccessService.for_organization(
            str(organization_id),
            repository,
            identities,
            _FactoryVerifier(),  # type: ignore[arg-type]
        )

    assert exc_info.value.code == "organization_scope_mismatch"
    assert exc_info.value.status_code == 404
    assert identities.organization_calls == []
    assert repository.policy_calls == 0
