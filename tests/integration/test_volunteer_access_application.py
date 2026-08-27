from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_access_service import VolunteerAccessService
from services.api.app.domain.tenant_context import TenantContext


class _Verifier:
    async def verify(self, token):
        return "Uapplicant"


class _IdentityRepository:
    def __init__(self):
        self.binding = None
        self.users = []

    async def get_line_binding(self, line_user_id):
        return self.binding

    async def get_organization(self, organization_id):
        return SimpleNamespace(id=organization_id, name="收容所 A", status="active")

    async def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        self.users.append(value)
        if value.__class__.__name__ == "LineUserBinding":
            self.binding = value
        return value


class _Repository:
    def __init__(self, *, enabled=True, insurance_required=False):
        self.organization_id = uuid4()
        self.enabled = enabled
        self.insurance_required = insurance_required
        self.values = []

    async def policy(self, *, for_update=False):
        return SimpleNamespace(
            applications_enabled=self.enabled,
            insurance_required=self.insurance_required,
            version=3,
        )

    async def pending_application_for_user(self, user_id, *, for_update=False):
        return next(
            (
                value
                for value in self.values
                if value.user_id == user_id and value.status == "pending"
            ),
            None,
        )

    async def applications_for_user(self, user_id, *, limit=50):
        return [value for value in self.values if value.user_id == user_id]

    async def application(self, application_id, *, for_update=False):
        return next((value for value in self.values if value.id == application_id), None)

    async def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        self.values.append(value)
        return value


class _PiiService:
    def __init__(self):
        self.calls = []

    async def create_profile(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(application_id=kwargs["application_id"])


class _DetailRepository:
    def __init__(
        self,
        organization_id,
        application,
        *,
        membership=True,
        membership_status="active",
    ):
        self.organization_id = organization_id
        self.application_value = application
        self.membership = membership
        self.membership_status = membership_status

    async def active_membership(self, user_id, *, for_update=False):
        if not self.membership or self.membership_status != "active":
            return None
        return SimpleNamespace(
            organization_id=self.organization_id,
            user_id=user_id,
            role="SHELTER_ADMIN",
            status="active",
        )

    async def application_detail(self, application_id, *, for_update=False):
        if self.application_value is None or self.application_value.id != application_id:
            return None
        return self.application_value, []


def _detail_application(organization_id):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        status="pending",
        submitted_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        decided_at=None,
        decision_reason=None,
        version=1,
    )


@pytest.mark.asyncio
async def test_application_detail_is_tenant_scoped_and_masks_profile_fields() -> None:
    organization_a = uuid4()
    application = _detail_application(organization_a)
    service = VolunteerAccessService(
        _DetailRepository(organization_a, application),
        _IdentityRepository(),
        _Verifier(),
    )

    detail = await service.application_detail(
        application.id,
        tenant_context=TenantContext(uuid4(), organization_a, "SHELTER_ADMIN"),
    )

    assert detail.application.id == application.id
    assert detail.service_dates == []
    serialized = repr(detail)
    assert "applicant_name" not in serialized
    assert "phone_number" not in serialized
    assert "ciphertext" not in serialized

    with pytest.raises(DomainError) as error:
        await service.application_detail(
            application.id,
            tenant_context=TenantContext(uuid4(), uuid4(), "SHELTER_ADMIN"),
        )
    assert error.value.code == "volunteer_application_not_found"
    assert error.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("membership_status", ["inactive", "suspended"])
async def test_application_detail_denies_inactive_or_suspended_membership(
    membership_status: str,
) -> None:
    organization_id = uuid4()
    application = _detail_application(organization_id)
    service = VolunteerAccessService(
        _DetailRepository(
            organization_id,
            application,
            membership_status=membership_status,
        ),
        _IdentityRepository(),
        _Verifier(),
    )

    with pytest.raises(DomainError) as error:
        await service.application_detail(
            application.id,
            tenant_context=TenantContext(uuid4(), organization_id, "SHELTER_ADMIN"),
        )
    assert error.value.code == "volunteer_application_not_found"
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_application_detail_missing_application_does_not_reveal_profile_state() -> None:
    organization_id = uuid4()
    service = VolunteerAccessService(
        _DetailRepository(organization_id, None),
        _IdentityRepository(),
        _Verifier(),
    )

    with pytest.raises(DomainError) as error:
        await service.application_detail(
            uuid4(),
            tenant_context=TenantContext(uuid4(), organization_id, "SHELTER_ADMIN"),
        )
    assert error.value.code == "volunteer_application_not_found"
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_submit_atomically_creates_identity_binding_and_pending_without_membership() -> None:
    repository = _Repository()
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())

    first = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
        now=datetime.now(timezone.utc),
    )
    second = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
        now=datetime.now(timezone.utc),
    )

    assert first.created is True
    assert second.created is False
    assert len(repository.values) == 1
    assert not any(
        value.__class__.__name__ == "OrganizationMembership" for value in identities.users
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "organization_code",
    ("FURKIDS-ASIA", "MOA-SHELTER-51", "MOA-SHELTER-58"),
)
async def test_fresh_line_identity_submits_pending_by_demo_organization_target(
    organization_code: str,
) -> None:
    repository = _Repository()
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())

    result = await service.submit(
        id_token=f"local-id-token:new-{organization_code.lower()}",
        entry_reference_id=None,
        organization_id=repository.organization_id,
        client_request_id=uuid4(),
        consent_acknowledged=True,
        now=datetime.now(timezone.utc),
    )

    assert result.created is True
    assert result.status.effective_status == "pending"
    assert result.status.application is not None
    assert result.status.application.organization_id == repository.organization_id
    assert result.status.application.source_channel == "liff"
    assert identities.binding is not None
    assert not any(
        value.__class__.__name__ == "OrganizationMembership" for value in identities.users
    )


@pytest.mark.asyncio
async def test_disabled_entry_blocks_new_submit_but_status_remains_available() -> None:
    repository = _Repository(enabled=False)
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())

    with pytest.raises(DomainError, match="暫停接受新申請"):
        await service.submit(
            id_token="token",
            entry_reference_id=uuid4(),
            client_request_id=uuid4(),
            consent_acknowledged=True,
        )

    status = await service.status(id_token="token", entry_reference_id=uuid4())
    assert status.effective_status == "none"


@pytest.mark.asyncio
async def test_withdraw_then_reapply_preserves_history_without_membership() -> None:
    repository = _Repository()
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())
    first = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
    )
    first.status.application.version = 1

    withdrawn = await service.withdraw(
        id_token="token",
        entry_reference_id=uuid4(),
        application_id=first.status.application.id,
        expected_version=1,
    )
    reapplied = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
    )

    assert withdrawn.effective_status == "withdrawn"
    assert reapplied.created is True
    assert len(repository.values) == 2
    assert repository.values[1].previous_application_id == repository.values[0].id


@pytest.mark.asyncio
async def test_disabled_entry_returns_existing_pending_duplicate() -> None:
    repository = _Repository(enabled=True)
    identities = _IdentityRepository()
    service = VolunteerAccessService(repository, identities, _Verifier())
    await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
    )
    repository.enabled = False

    replay = await service.submit(
        id_token="token",
        entry_reference_id=uuid4(),
        client_request_id=uuid4(),
        consent_acknowledged=True,
    )

    assert replay.created is False
    assert replay.status.effective_status == "pending"


@pytest.mark.asyncio
async def test_submit_supports_organization_target_and_persists_profile_input() -> None:
    repository = _Repository()
    identities = _IdentityRepository()
    pii = _PiiService()
    service = VolunteerAccessService(repository, identities, _Verifier(), pii_service=pii)

    result = await service.submit(
        id_token="token",
        entry_reference_id=None,
        client_request_id=uuid4(),
        consent_acknowledged=True,
        organization_id=repository.organization_id,
        applicant_name="測試志工",
        phone_number="0900000000",
        basic_profile={"experience": "短期照護"},
        insurance_identity=None,
        insurance_consent_acknowledged=False,
    )

    assert result.created is True
    assert result.status.application is not None
    assert result.status.application.organization_id == repository.organization_id
    assert len(pii.calls) == 1
    assert pii.calls[0]["applicant_name"] == "測試志工"
    assert pii.calls[0]["phone_number"] == "0900000000"
    assert pii.calls[0]["basic_profile"] == {"experience": "短期照護"}
    assert pii.calls[0]["insurance_identity"] is None
    assert not any(
        value.__class__.__name__ == "OrganizationMembership" for value in identities.users
    )


@pytest.mark.asyncio
async def test_submit_rejects_insurance_identity_when_policy_does_not_require_it() -> None:
    repository = _Repository(insurance_required=False)
    identities = _IdentityRepository()
    pii = _PiiService()
    service = VolunteerAccessService(repository, identities, _Verifier(), pii_service=pii)

    with pytest.raises(DomainError, match="不需保險身分資料"):
        await service.submit(
            id_token="token",
            entry_reference_id=None,
            organization_id=repository.organization_id,
            client_request_id=uuid4(),
            consent_acknowledged=True,
            applicant_name="測試志工",
            phone_number="0900000000",
            insurance_identity="A123456789",
            insurance_consent_acknowledged=True,
        )

    assert repository.values == []
    assert pii.calls == []


@pytest.mark.asyncio
async def test_submit_requires_insurance_identity_when_policy_requires_it() -> None:
    repository = _Repository(insurance_required=True)
    identities = _IdentityRepository()
    pii = _PiiService()
    service = VolunteerAccessService(repository, identities, _Verifier(), pii_service=pii)

    with pytest.raises(DomainError, match="提供保險身分資料"):
        await service.submit(
            id_token="token",
            entry_reference_id=None,
            organization_id=repository.organization_id,
            client_request_id=uuid4(),
            consent_acknowledged=True,
            applicant_name="測試志工",
            phone_number="0900000000",
            insurance_identity=None,
            insurance_consent_acknowledged=False,
        )

    assert repository.values == []
    assert pii.calls == []
