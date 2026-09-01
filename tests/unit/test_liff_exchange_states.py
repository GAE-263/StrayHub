from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.application.ports.authentication import ActiveVolunteerEntryReference
from services.api.app.persistence.models.identity import (
    RefreshTokenRecord,
    SessionRecord,
    WebhookSession,
)


class FakePasswordHasher:
    def hash(self, password: str) -> str:
        return password

    def verify(self, password: str, encoded_hash: str) -> bool:
        return password == encoded_hash

    def needs_rehash(self, encoded_hash: str) -> bool:
        return False


class FakeAccessToken:
    def issue(self, claims):
        return f"internal:{claims['sid']}"

    def verify(self, token: str):
        return {}


class FakeLineVerifier:
    async def verify(self, token: str) -> str:
        if token != "valid-line-id-token":
            raise ValueError("invalid LINE token")
        return "U-line-user"


class FakeEntryResolver:
    def __init__(self, organization_id: UUID, *, valid: bool = True) -> None:
        self.organization_id = organization_id
        self.valid = valid

    async def resolve(self, raw_reference: str):
        if not self.valid or raw_reference != "valid-entry-reference":
            return None
        return ActiveVolunteerEntryReference(
            uuid4(),
            self.organization_id,
            "ORG-B",
            "收容所 B",
        )


class FailingEntryResolver:
    async def resolve(self, raw_reference: str):
        raise RuntimeError(f"resolver leaked {raw_reference}")


class EntryResolverMustNotRun:
    async def resolve(self, raw_reference: str):
        raise AssertionError(f"invalid identity must not resolve {raw_reference}")


class FakeRepository:
    def __init__(self) -> None:
        self.user = SimpleNamespace(id=uuid4(), status="active")
        self.binding = SimpleNamespace(user_id=self.user.id)
        self.target_organization = SimpleNamespace(
            id=uuid4(), code="ORG-B", name="收容所 B", status="active"
        )
        self.other_organization = SimpleNamespace(
            id=uuid4(), code="ORG-A", name="收容所 A", status="active"
        )
        self.target_membership = SimpleNamespace(
            id=uuid4(),
            user_id=self.user.id,
            organization_id=self.target_organization.id,
            role="VOLUNTEER",
            status="active",
        )
        self.other_membership = SimpleNamespace(
            id=uuid4(),
            user_id=self.user.id,
            organization_id=self.other_organization.id,
            role="VOLUNTEER",
            status="active",
        )
        self.effective_membership = self.target_membership
        self.effective_grant: SimpleNamespace | None = SimpleNamespace(
            id=uuid4(),
            membership_id=self.target_membership.id,
            user_id=self.user.id,
            organization_id=self.target_organization.id,
            status="active",
        )
        self.raw_membership = self.target_membership
        self.latest_application = None
        self.values: list[object] = []
        self.scoped_to: tuple[UUID, UUID] | None = None
        self.authorization_calls: list[str] = []

    async def get_line_binding(self, line_user_id: str):
        return self.binding if line_user_id == "U-line-user" else None

    async def set_authentication_user_scope(self, user_id: UUID) -> None:
        self.authorization_calls.append("user_scope")

    async def effective_organization_access(self, user_id: UUID):
        assert user_id == self.user.id
        return [
            (self.target_membership, self.target_organization),
            (self.other_membership, self.other_organization),
        ]

    async def revoke_active_webhook_sessions(self, user_id: UUID) -> None:
        assert user_id == self.user.id
        self.authorization_calls.append("revoke_webhook_sessions")

    async def lock_line_binding(self, line_user_id: str):
        self.authorization_calls.append("binding")
        return self.binding if line_user_id == "U-line-user" else None

    async def get_user(self, user_id: UUID):
        return self.user if user_id == self.user.id else None

    async def set_authentication_context_scope(self, user_id: UUID, organization_id: UUID) -> None:
        self.scoped_to = (user_id, organization_id)
        self.authorization_calls.append("scope")

    async def lock_user(self, user_id: UUID):
        self.authorization_calls.append("user")
        return self.user if user_id == self.user.id else None

    async def get_organization(self, organization_id: UUID):
        for organization in (self.target_organization, self.other_organization):
            if organization.id == organization_id:
                return organization
        return None

    async def lock_effective_volunteer_access(self, user_id: UUID, organization_id: UUID):
        assert self.scoped_to == (user_id, organization_id)
        self.authorization_calls.append("membership_grant")
        membership = self.effective_membership
        if (
            membership is not None
            and self.effective_grant is not None
            and membership.user_id == user_id
            and membership.organization_id == organization_id
        ):
            return membership, self.effective_grant
        return None

    async def get_membership(self, user_id: UUID, organization_id: UUID):
        assert self.scoped_to == (user_id, organization_id)
        membership = self.raw_membership
        if (
            membership is not None
            and membership.user_id == user_id
            and membership.organization_id == organization_id
        ):
            return membership
        return None

    async def latest_volunteer_application(self, user_id: UUID, organization_id: UUID):
        assert self.scoped_to == (user_id, organization_id)
        return self.latest_application

    async def add(self, value):
        self.values.append(value)
        return value


def service(repository: FakeRepository, *, entry_valid: bool = True) -> SessionService:
    return SessionService(
        repository,
        password_hasher=FakePasswordHasher(),
        access_token=FakeAccessToken(),
        line_verifier=FakeLineVerifier(),
        entry_resolver=FakeEntryResolver(
            repository.target_organization.id,
            valid=entry_valid,
        ),
    )


@pytest.mark.asyncio
async def test_line_bind_requires_explicit_selection_for_multiple_memberships() -> None:
    repository = FakeRepository()

    result = await service(repository).bind_line_identity(id_token="valid-line-id-token")

    assert result["state"] == "selection_required"
    assert {item["id"] for item in result["organizations"]} == {
        repository.target_organization.id,
        repository.other_organization.id,
    }
    assert repository.values == []


@pytest.mark.asyncio
async def test_line_bind_selected_membership_sets_exact_session_context() -> None:
    repository = FakeRepository()
    repository.target_membership.role = "STAFF"

    result = await service(repository).bind_line_identity(
        id_token="valid-line-id-token",
        organization_id=repository.target_organization.id,
    )

    assert result["organization_id"] == repository.target_organization.id
    assert repository.scoped_to == (repository.user.id, repository.target_organization.id)
    assert "revoke_webhook_sessions" in repository.authorization_calls
    assert any(
        isinstance(value, SessionRecord)
        and value.active_organization_id == repository.target_organization.id
        for value in repository.values
    )
    assert any(
        isinstance(value, WebhookSession)
        and value.organization_id == repository.target_organization.id
        for value in repository.values
    )


@pytest.mark.asyncio
async def test_line_bind_rejects_unowned_shelter_selection() -> None:
    repository = FakeRepository()

    with pytest.raises(DomainError) as caught:
        await service(repository).bind_line_identity(
            id_token="valid-line-id-token",
            organization_id=uuid4(),
        )

    assert caught.value.code == "shelter_context_denied"
    assert repository.values == []


@pytest.mark.asyncio
async def test_active_exchange_selects_entry_organization_with_multiple_memberships() -> None:
    repository = FakeRepository()

    result = await service(repository).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "ACTIVE"
    assert result["organization"] == {
        "id": repository.target_organization.id,
        "code": "ORG-B",
        "name": "收容所 B",
    }
    assert result["user"]["role"] == "VOLUNTEER"
    assert result["next_path"] == "/animal-confirmation"
    assert result["access_token"].startswith("internal:")
    assert repository.scoped_to == (
        repository.user.id,
        repository.target_organization.id,
    )
    assert repository.authorization_calls == [
        "binding",
        "scope",
        "user",
        "membership_grant",
    ]
    sessions = [value for value in repository.values if isinstance(value, SessionRecord)]
    assert len(sessions) == 1
    assert sessions[0].active_organization_id == repository.target_organization.id
    assert len([value for value in repository.values if isinstance(value, RefreshTokenRecord)]) == 1


@pytest.mark.asyncio
async def test_new_line_identity_returns_new_without_creating_session() -> None:
    repository = FakeRepository()
    repository.binding = None

    result = await service(repository).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "NEW"
    assert result["next_path"] == "/volunteer-application"
    assert "access_token" not in result
    assert repository.values == []


@pytest.mark.asyncio
async def test_pending_application_returns_pending_without_creating_session() -> None:
    repository = FakeRepository()
    repository.effective_membership = None
    repository.raw_membership = None
    repository.latest_application = SimpleNamespace(status="pending")

    result = await service(repository).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "PENDING"
    assert "access_token" not in result
    assert repository.values == []


@pytest.mark.asyncio
async def test_suspended_membership_returns_suspended_without_creating_session() -> None:
    repository = FakeRepository()
    repository.effective_membership = None
    repository.raw_membership.status = "suspended"

    result = await service(repository).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "SUSPENDED"
    assert "access_token" not in result
    assert repository.values == []


@pytest.mark.asyncio
async def test_missing_effective_grant_returns_suspended_without_creating_session() -> None:
    repository = FakeRepository()
    repository.effective_grant = None

    result = await service(repository).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "SUSPENDED"
    assert "access_token" not in result
    assert repository.values == []


@pytest.mark.asyncio
async def test_membership_in_other_organization_does_not_authorize_entry() -> None:
    repository = FakeRepository()
    repository.effective_membership = repository.other_membership
    repository.raw_membership = repository.other_membership

    result = await service(repository).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "NEW"
    assert "access_token" not in result
    assert repository.values == []


@pytest.mark.asyncio
async def test_inactive_user_is_suspended_and_issues_no_session() -> None:
    repository = FakeRepository()
    repository.user.status = "suspended"

    result = await service(repository).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "SUSPENDED"
    assert "access_token" not in result
    assert repository.values == []


@pytest.mark.asyncio
async def test_expired_or_invalid_entry_is_rejected_before_session_creation() -> None:
    repository = FakeRepository()

    with pytest.raises(DomainError) as error:
        await service(repository, entry_valid=False).exchange_line_identity(
            id_token="valid-line-id-token",
            shelter_entry_reference="expired-entry-reference",
        )

    assert error.value.code == "entry_unavailable"
    assert repository.values == []


@pytest.mark.asyncio
async def test_invalid_line_token_is_mapped_to_safe_unauthorized_error() -> None:
    repository = FakeRepository()

    with pytest.raises(DomainError) as error:
        await service(repository).exchange_line_identity(
            id_token="invalid",
            shelter_entry_reference="valid-entry-reference",
        )

    assert error.value.code == "invalid_line_id_token"
    assert error.value.status_code == 401
    assert repository.values == []


@pytest.mark.asyncio
async def test_invalid_line_token_is_rejected_before_entry_resolution() -> None:
    repository = FakeRepository()
    identity_first_service = SessionService(
        repository,
        password_hasher=FakePasswordHasher(),
        access_token=FakeAccessToken(),
        line_verifier=FakeLineVerifier(),
        entry_resolver=EntryResolverMustNotRun(),
    )

    with pytest.raises(DomainError) as error:
        await identity_first_service.exchange_line_identity(
            id_token="invalid",
            shelter_entry_reference="must-not-be-resolved",
        )

    assert error.value.code == "invalid_line_id_token"
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_entry_resolver_failure_returns_safe_dependency_error() -> None:
    repository = FakeRepository()
    failing_service = SessionService(
        repository,
        password_hasher=FakePasswordHasher(),
        access_token=FakeAccessToken(),
        line_verifier=FakeLineVerifier(),
        entry_resolver=FailingEntryResolver(),
    )

    with pytest.raises(DomainError) as error:
        await failing_service.exchange_line_identity(
            id_token="valid-line-id-token",
            shelter_entry_reference="valid-entry-reference",
        )

    assert error.value.status_code == 503
    assert error.value.code == "liff_exchange_unavailable"
    assert error.value.message == "志工入口暫時無法使用"


@pytest.mark.asyncio
async def test_database_failure_returns_safe_dependency_error() -> None:
    repository = FakeRepository()

    async def fail_binding(line_user_id: str):
        assert line_user_id == "U-line-user"
        raise RuntimeError("database connection details")

    repository.lock_line_binding = fail_binding

    with pytest.raises(DomainError) as error:
        await service(repository).exchange_line_identity(
            id_token="valid-line-id-token",
            shelter_entry_reference="valid-entry-reference",
        )

    assert error.value.status_code == 503
    assert error.value.code == "liff_exchange_unavailable"
    assert error.value.message == "志工入口暫時無法使用"


class RecordingRichMenuRouter:
    """記錄 link_for_user 呼叫；optional 用來模擬 LINE API 失敗。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.fail = fail

    async def link_for_user(
        self,
        *,
        line_user_id: str,
        role: str | None,
        organization_selected: bool = False,
    ) -> None:
        self.calls.append((line_user_id, role))
        if self.fail:
            raise RuntimeError("LINE API 暫時不可用")


def service_with_router(
    repository: FakeRepository,
    router: RecordingRichMenuRouter,
    *,
    entry_valid: bool = True,
) -> SessionService:
    return SessionService(
        repository,
        password_hasher=FakePasswordHasher(),
        access_token=FakeAccessToken(),
        line_verifier=FakeLineVerifier(),
        entry_resolver=FakeEntryResolver(
            repository.target_organization.id,
            valid=entry_valid,
        ),
        rich_menu_router=router,
    )


@pytest.mark.asyncio
async def test_active_exchange_links_volunteer_rich_menu() -> None:
    """志工走 entry 交換身分，不經過 /v1/line/bind，這條路徑也必須切選單。"""
    repository = FakeRepository()
    router = RecordingRichMenuRouter()

    result = await service_with_router(repository, router).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "ACTIVE"
    assert router.calls == [("U-line-user", "VOLUNTEER")]


@pytest.mark.asyncio
async def test_non_active_exchange_does_not_link_rich_menu() -> None:
    repository = FakeRepository()
    router = RecordingRichMenuRouter()

    with pytest.raises(DomainError):
        await service_with_router(repository, router, entry_valid=False).exchange_line_identity(
            id_token="valid-line-id-token",
            shelter_entry_reference="valid-entry-reference",
        )

    assert router.calls == []


@pytest.mark.asyncio
async def test_rich_menu_failure_does_not_break_exchange() -> None:
    """選單切換是 best-effort；LINE API 失敗不得讓志工換不到 session。"""
    repository = FakeRepository()
    router = RecordingRichMenuRouter(fail=True)

    result = await service_with_router(repository, router).exchange_line_identity(
        id_token="valid-line-id-token",
        shelter_entry_reference="valid-entry-reference",
    )

    assert result["state"] == "ACTIVE"
    assert result["access_token"].startswith("internal:")
    assert router.calls == [("U-line-user", "VOLUNTEER")]
