from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Response
from pydantic import ValidationError
from services.api.app.api import volunteer_access as api
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_access_service import (
    PublicOrganizationResult,
    VolunteerStatusResult,
    VolunteerSubmitResult,
)
from services.api.app.domain.volunteer_target import EntryTarget, OrganizationTarget
from sqlalchemy.exc import SQLAlchemyError

VALID_REFERENCE = "opaque-entry-reference-0123456789abcdef"
ORG_A = uuid4()


def test_identity_request_has_fixed_target_fields_and_rejects_client_display_fields() -> None:
    assert set(api.VolunteerIdentityRequest.model_fields) == {
        "id_token",
        "organization_id",
        "shelter_entry_reference",
    }
    assert api.VolunteerIdentityRequest.model_fields["organization_id"].default is None
    assert api.VolunteerIdentityRequest.model_fields["shelter_entry_reference"].default is None

    with pytest.raises(ValidationError):
        api.VolunteerIdentityRequest.model_validate(
            {
                "id_token": "synthetic-token",
                "organization_id": ORG_A,
                "organization_name": "client-controlled name",
                "organization_code": "CLIENT-CODE",
            }
        )


def test_identity_request_builds_organization_or_legacy_entry_target() -> None:
    organization_request = api.VolunteerIdentityRequest(
        id_token="synthetic-token", organization_id=ORG_A, shelter_entry_reference=None
    )
    entry_request = api.VolunteerIdentityRequest(
        id_token="synthetic-token", organization_id=None, shelter_entry_reference=VALID_REFERENCE
    )

    assert isinstance(organization_request.target, OrganizationTarget)
    assert organization_request.target.organization_id == ORG_A
    assert isinstance(entry_request.target, EntryTarget)
    assert entry_request.target.shelter_entry_reference == VALID_REFERENCE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("organization_id", "shelter_entry_reference"),
    ((None, None), (ORG_A, VALID_REFERENCE)),
)
async def test_status_request_target_cardinality_is_http_422(
    organization_id: UUID | None, shelter_entry_reference: str | None
) -> None:
    app = FastAPI()
    app.post("/status")(api.resolve_volunteer_application_status)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/status",
            json={
                "id_token": "synthetic-token",
                "organization_id": None if organization_id is None else str(organization_id),
                "shelter_entry_reference": shelter_entry_reference,
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_status_request_invalid_organization_uuid_is_http_422() -> None:
    app = FastAPI()
    app.post("/status")(api.resolve_volunteer_application_status)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/status",
            json={
                "id_token": "synthetic-token",
                "organization_id": "not-a-uuid",
                "shelter_entry_reference": None,
            },
        )

    assert response.status_code == 422


class _ScopedRepository:
    created: list[UUID] = []

    def __init__(self, _session, organization_id: UUID) -> None:
        self.organization_id = organization_id
        self.__class__.created.append(organization_id)


class _FakeStatusService:
    def __init__(
        self,
        result: VolunteerStatusResult,
        *,
        expected_verified_line_user_id: str | None = None,
    ) -> None:
        self.result = result
        self.expected_verified_line_user_id = expected_verified_line_user_id

    async def status(
        self,
        *,
        id_token: str,
        entry_reference_id: UUID | None,
        verified_line_user_id: str | None = None,
    ) -> VolunteerStatusResult:
        assert id_token == "synthetic-token"
        assert entry_reference_id is None
        assert verified_line_user_id == self.expected_verified_line_user_id
        return self.result


def _status_result(effective_status: str) -> VolunteerStatusResult:
    application = None
    grant = None
    if effective_status in {"pending", "active"}:
        application = SimpleNamespace(
            id=uuid4(),
            organization_id=ORG_A,
            display_name="LINE 志工",
            status="pending" if effective_status == "pending" else "approved",
            submitted_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
            decided_at=None,
            decision_reason=None,
            version=1,
        )
    if effective_status == "active":
        grant = SimpleNamespace(
            id=uuid4(),
            status="active",
            source_type="manager_approval",
            policy_version_used=1,
            duration_hours_used=24,
            valid_from=datetime(2026, 8, 23, tzinfo=timezone.utc),
            expires_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
            version=1,
        )
    return VolunteerStatusResult(
        organization=PublicOrganizationResult(ORG_A, "Shelter A", True),
        application=application,
        grant=grant,
        effective_status=effective_status,
        next_actions=[],
    )


def test_management_mutation_requests_forbid_unknown_and_duplicate_fields() -> None:
    with pytest.raises(ValidationError):
        api.VolunteerAccessPolicyUpdateRequest.model_validate({"expected_version": 1})
    with pytest.raises(ValidationError):
        api.VolunteerAccessPolicyUpdateRequest.model_validate(
            {"expected_version": 1, "applications_enabled": None}
        )

    with pytest.raises(ValidationError):
        api.VolunteerAccessPolicyUpdateRequest.model_validate(
            {"expected_version": 1, "unexpected": "discarded"}
        )

    item = {"application_id": str(uuid4()), "expected_version": 1}
    with pytest.raises(ValidationError):
        api.VolunteerDecisionBatchRequest.model_validate(
            {
                "operation_id": str(uuid4()),
                "decision": "approve",
                "selection": {"mode": "explicit_items", "items": [item, item]},
            }
        )

    notification_id = str(uuid4())
    with pytest.raises(ValidationError):
        api.VolunteerNotificationRetryRequest.model_validate(
            {
                "operation_id": str(uuid4()),
                "notification_ids": [notification_id, notification_id],
            }
        )


def test_response_maps_application_without_orm_display_name() -> None:
    result = VolunteerStatusResult(
        organization=PublicOrganizationResult(ORG_A, "Shelter A", True),
        application=SimpleNamespace(
            id=uuid4(),
            organization_id=ORG_A,
            status="pending",
            submitted_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
            decided_at=None,
            decision_reason=None,
            version=1,
        ),
        grant=None,
        effective_status="pending",
        next_actions=["wait"],
    )

    response = api._response(result)

    assert response.application is not None
    assert response.application.display_name == "LINE 志工"


def test_batch_dict_projects_snapshot_policy_metadata() -> None:
    batch = SimpleNamespace(
        id=uuid4(),
        organization_id=ORG_A,
        operation_id=uuid4(),
        decision="approve",
        selection_mode="explicit_items",
        snapshot_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        policy_version_used=3,
        default_duration_hours_used=72,
        status="queued",
        requested_count=1,
        processed_count=0,
        succeeded_count=0,
        conflict_count=0,
        failed_count=0,
        completed_at=None,
        created_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
    )

    response = api._batch_dict(batch)

    assert response["policy_version_used"] == 3
    assert response["default_duration_hours_used"] == 72


@pytest.mark.asyncio
@pytest.mark.parametrize("effective_status", ["none", "pending", "active"])
async def test_hub_organization_status_uses_target_org_and_preserves_public_status(
    monkeypatch: pytest.MonkeyPatch, effective_status: str
) -> None:
    _ScopedRepository.created = []
    service = _FakeStatusService(
        _status_result(effective_status), expected_verified_line_user_id="line-user"
    )
    factory_calls: list[UUID] = []

    class _Verifier:
        async def verify(self, _token: str) -> str:
            return "line-user"

    async def set_scope(_session, _organization_id: UUID) -> None:
        return None

    async def for_organization_status(
        organization_id: UUID,
        repository: _ScopedRepository,
        identities,
        verifier,
        *,
        audit,
        notifications,
    ) -> _FakeStatusService:
        assert repository.organization_id == organization_id
        factory_calls.append(organization_id)
        return service

    monkeypatch.setattr(api, "VolunteerAccessRepository", _ScopedRepository)
    monkeypatch.setattr(api, "set_organization_scope", set_scope, raising=False)
    monkeypatch.setattr(
        api.VolunteerAccessService, "for_organization_status", for_organization_status
    )

    payload = api.VolunteerIdentityRequest(
        id_token="synthetic-token", organization_id=ORG_A, shelter_entry_reference=None
    )
    response = await api.resolve_volunteer_application_status(payload, object(), _Verifier())

    assert response.organization.id == ORG_A
    assert response.organization.name == "Shelter A"
    assert response.effective_status == effective_status
    assert factory_calls == [ORG_A]
    assert _ScopedRepository.created == [ORG_A]


@pytest.mark.asyncio
async def test_organization_status_verifies_identity_and_sets_exact_scope_before_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    service = _FakeStatusService(
        _status_result("none"), expected_verified_line_user_id="verified-line-user"
    )

    class _Verifier:
        async def verify(self, token: str) -> str:
            events.append(("verify", token))
            return "verified-line-user"

    async def set_scope(_session, organization_id: UUID) -> None:
        events.append(("scope", organization_id))

    async def status_factory(
        organization_id: UUID,
        repository: _ScopedRepository,
        identities,
        verifier,
        *,
        audit,
        notifications,
    ) -> _FakeStatusService:
        events.append(("lookup", organization_id))
        assert repository.organization_id == ORG_A
        assert isinstance(verifier, _Verifier)
        return service

    async def submit_factory(*_args, **_kwargs):
        raise AssertionError("status must not use the submit-only organization factory")

    monkeypatch.setattr(api, "VolunteerAccessRepository", _ScopedRepository)
    monkeypatch.setattr(api, "set_organization_scope", set_scope, raising=False)
    monkeypatch.setattr(
        api.VolunteerAccessService, "for_organization_status", status_factory, raising=False
    )
    monkeypatch.setattr(api.VolunteerAccessService, "for_organization", submit_factory)

    payload = api.VolunteerIdentityRequest(
        id_token="synthetic-token", organization_id=ORG_A, shelter_entry_reference=None
    )
    response = await api.resolve_volunteer_application_status(payload, object(), _Verifier())

    assert response.effective_status == "none"
    assert events == [
        ("verify", "synthetic-token"),
        ("scope", ORG_A),
        ("lookup", ORG_A),
    ]


@pytest.mark.asyncio
async def test_legacy_entry_status_still_uses_existing_entry_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_id = uuid4()
    expected_service = object()
    calls: list[str] = []

    async def legacy_resolver(_session, raw_reference, _verifier):
        calls.append(raw_reference)
        return expected_service, reference_id

    monkeypatch.setattr(api, "_service_for_entry", legacy_resolver)

    class _LegacyService:
        async def status(
            self,
            *,
            id_token: str,
            entry_reference_id: UUID,
            verified_line_user_id: str,
        ):
            assert id_token == "synthetic-token"
            assert entry_reference_id == reference_id
            assert verified_line_user_id == "synthetic-line-user"
            return _status_result("none")

    async def resolver(_session, raw_reference, verifier):
        calls.append(raw_reference)
        return _LegacyService(), reference_id

    monkeypatch.setattr(api, "_service_for_entry", resolver)
    payload = api.VolunteerIdentityRequest(
        id_token="synthetic-token", organization_id=None, shelter_entry_reference=VALID_REFERENCE
    )

    class _Verifier:
        async def verify(self, _token: str) -> str:
            return "synthetic-line-user"

    response = await api.resolve_volunteer_application_status(payload, object(), _Verifier())

    assert response.effective_status == "none"
    assert calls == [VALID_REFERENCE]


def test_status_route_does_not_accept_client_organization_name_or_code() -> None:
    route = next(
        route
        for route in api.router.routes
        if getattr(route, "path", None) == "/v1/volunteer-applications/status"
    )
    assert "organization_name" not in route.endpoint.__annotations__
    assert "organization_code" not in route.endpoint.__annotations__


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["status", "submit", "withdraw"])
async def test_invalid_line_token_is_verified_before_legacy_entry_resolution(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    async def forbidden_resolver(*_args, **_kwargs):
        raise AssertionError("entry resolver must not run for an invalid LINE token")

    monkeypatch.setattr(api, "_service_for_entry", forbidden_resolver)

    class _InvalidVerifier:
        async def verify(self, _token: str) -> str:
            raise DomainError("invalid_line_id_token", "無法確認 LINE 身分", 401)

    payload: api.VolunteerIdentityRequest
    if operation == "submit":
        payload = api.VolunteerApplicationCreateRequest(
            id_token="synthetic-token",
            shelter_entry_reference=VALID_REFERENCE,
            client_request_id=uuid4(),
            consent_acknowledged=True,
        )
    elif operation == "withdraw":
        payload = api.VolunteerApplicationWithdrawRequest(
            id_token="synthetic-token",
            shelter_entry_reference=VALID_REFERENCE,
            expected_version=1,
        )
    else:
        payload = api.VolunteerIdentityRequest(
            id_token="synthetic-token",
            shelter_entry_reference=VALID_REFERENCE,
        )

    with pytest.raises(DomainError) as error:
        if operation == "submit":
            await api.submit_volunteer_application(
                payload, Response(), object(), _InvalidVerifier()
            )
        elif operation == "withdraw":
            await api.withdraw_volunteer_application(uuid4(), payload, object(), _InvalidVerifier())
        else:
            await api.resolve_volunteer_application_status(payload, object(), _InvalidVerifier())

    assert error.value.code == "invalid_line_id_token"
    assert error.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["submit", "withdraw"])
async def test_mutations_validate_response_before_commit(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    class _Session:
        commits = 0

        async def commit(self) -> None:
            self.commits += 1

    class _Verifier:
        async def verify(self, _token: str) -> str:
            return "verified-line-user"

    class _Service:
        async def submit(self, **_kwargs) -> VolunteerSubmitResult:
            return VolunteerSubmitResult(_status_result("none"), True)

        async def withdraw(self, **_kwargs) -> VolunteerStatusResult:
            return _status_result("none")

    async def resolver(_session, _reference, _verifier):
        return _Service(), uuid4()

    def fail_response(_result):
        raise RuntimeError("response validation failed")

    monkeypatch.setattr(api, "_service_for_entry", resolver)
    monkeypatch.setattr(api, "_response", fail_response)
    session = _Session()
    verifier = _Verifier()
    if operation == "submit":
        payload = api.VolunteerApplicationCreateRequest(
            id_token="synthetic-token",
            shelter_entry_reference=VALID_REFERENCE,
            client_request_id=uuid4(),
            consent_acknowledged=True,
        )
        with pytest.raises(RuntimeError, match="response validation failed"):
            await api.submit_volunteer_application(payload, Response(), session, verifier)
    else:
        payload = api.VolunteerApplicationWithdrawRequest(
            id_token="synthetic-token",
            shelter_entry_reference=VALID_REFERENCE,
            expected_version=1,
        )
        with pytest.raises(RuntimeError, match="response validation failed"):
            await api.withdraw_volunteer_application(uuid4(), payload, session, verifier)

    assert session.commits == 0


@pytest.mark.parametrize("operation", ["submit", "withdraw"])
def test_organization_target_mutations_are_rejected_by_entry_only_request_models(
    operation: str,
) -> None:
    with pytest.raises(ValidationError):
        if operation == "submit":
            api.VolunteerApplicationCreateRequest(
                id_token="synthetic-token",
                organization_id=ORG_A,
                shelter_entry_reference=None,
                client_request_id=uuid4(),
                consent_acknowledged=True,
            )
        else:
            api.VolunteerApplicationWithdrawRequest(
                id_token="synthetic-token",
                organization_id=ORG_A,
                shelter_entry_reference=None,
                expected_version=1,
            )


@pytest.mark.asyncio
async def test_public_directory_maps_repository_sqlalchemy_error_to_stable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingRepository:
        def __init__(self, _session) -> None:
            pass

        async def list_public_volunteer_organizations(self):
            raise SQLAlchemyError("synthetic database failure")

    monkeypatch.setattr(api, "OrganizationRepository", _FailingRepository)

    with pytest.raises(DomainError) as error:
        await api.list_public_volunteer_organizations(object())

    assert error.value.code == "dependency_unavailable"
    assert error.value.status_code == 503
